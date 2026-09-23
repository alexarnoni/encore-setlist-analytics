"""Database I/O for the survival analysis (spec-03 T8).

Reads the per-show song sets (`intermediate.int_show_song_sets`) and catalog
facts (`intermediate.int_performances`, `intermediate.int_song_catalog`)
while raw setlist.fm data is still around — the same window `transform`'s dbt
run has — computes survival outcomes and Kaplan-Meier curves per band with
the pure functions in `encore.analysis.survival`, and writes the three
survival marts. Nothing here reads or writes anything outside `analytics`
except the three named read-only queries below.

The three marts are refreshed by this module, not by dbt (design decision
D4, spec-03-progress.md): `ensure_tables` creates them if missing, and
`write_survival_marts` replaces their content in one transaction (DELETE +
INSERT), so a failed run leaves the previous, still-consistent content in
place, and a rerun on the same data is idempotent bar `computed_at`. dbt only
documents and tests them afterwards (T9).
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from psycopg2.extras import execute_values

from encore.analysis.survival import (
    WINDOWS,
    ShowAppearance,
    SongCatalogInfo,
    SongSurvival,
    compute_survival,
    fit_curve,
    group_by_album,
)

# The window mart_song_survival's own columns (duration_shows_n50, event_n50)
# are named after — the headline single-window view of survival, matching
# product.md's default N. mart_survival_curves/summary carry every window in
# WINDOWS, this one included.
SONG_MART_WINDOW = 50


def ensure_tables(conn) -> None:
    """Create the three survival marts if they don't exist yet (idempotent)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS analytics.mart_song_survival (
                band TEXT NOT NULL,
                song_title TEXT NOT NULL,
                reference_album TEXT,
                release_year INTEGER,
                performances INTEGER NOT NULL,
                debut_year INTEGER NOT NULL,
                last_year INTEGER NOT NULL,
                duration_shows_n50 INTEGER NOT NULL,
                event_n50 BOOLEAN NOT NULL,
                returned_after_abandonment BOOLEAN NOT NULL,
                computed_at TIMESTAMPTZ NOT NULL,
                PRIMARY KEY (band, song_title)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS analytics.mart_survival_curves (
                band TEXT NOT NULL,
                album TEXT NOT NULL,
                n_window INTEGER NOT NULL,
                t_shows INTEGER NOT NULL,
                at_risk INTEGER NOT NULL,
                events INTEGER NOT NULL,
                survival_probability NUMERIC NOT NULL,
                ci_lower NUMERIC NOT NULL,
                ci_upper NUMERIC NOT NULL,
                computed_at TIMESTAMPTZ NOT NULL,
                PRIMARY KEY (band, album, n_window, t_shows)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS analytics.mart_survival_summary (
                band TEXT NOT NULL,
                album TEXT NOT NULL,
                n_window INTEGER NOT NULL,
                songs INTEGER NOT NULL,
                events INTEGER NOT NULL,
                censored INTEGER NOT NULL,
                median_survival_shows NUMERIC,
                computed_at TIMESTAMPTZ NOT NULL,
                PRIMARY KEY (band, album, n_window)
            )
            """
        )
    conn.commit()


def fetch_show_appearances(conn) -> list[ShowAppearance]:
    """Every (show, song) row from int_show_song_sets, across all bands."""
    with conn.cursor() as cur:
        cur.execute("SELECT band, song_key, show_key, show_date FROM intermediate.int_show_song_sets")
        return [ShowAppearance(band, song_key, show_key, show_date) for band, song_key, show_key, show_date in cur.fetchall()]


def fetch_performance_counts(conn) -> dict[str, dict[str, int]]:
    """{band: {song_key: performance_count}}. Matched, dated performances
    only — the same population int_show_song_sets and the marts use, so a
    song's eligibility here matches what its appearances actually show."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT band, title_normalized, count(*)
            FROM intermediate.int_performances
            WHERE is_matched AND show_year IS NOT NULL
            GROUP BY band, title_normalized
            """
        )
        counts: dict[str, dict[str, int]] = {}
        for band, song_key, performances in cur.fetchall():
            counts.setdefault(band, {})[song_key] = performances
        return counts


def fetch_catalog(conn) -> dict[str, dict[str, SongCatalogInfo]]:
    """{band: {song_key: SongCatalogInfo}} for every catalog song."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT band, title_normalized, song_title, reference_album, release_year "
            "FROM intermediate.int_song_catalog"
        )
        catalog: dict[str, dict[str, SongCatalogInfo]] = {}
        for band, song_key, song_title, reference_album, release_year in cur.fetchall():
            catalog.setdefault(band, {})[song_key] = SongCatalogInfo(song_title, reference_album, release_year)
        return catalog


def _show_years_by_index(appearances: list[ShowAppearance], band: str) -> dict[int, int]:
    """1-based show index -> the calendar year of that show (years only, per
    R7 — never a full date). Reuses survival's own show-index logic so this
    always agrees with what compute_survival based its indices on."""
    from encore.analysis.survival import band_show_index

    index = band_show_index(appearances, band)
    dates_by_key: dict[str, date] = {}
    for appearance in appearances:
        if appearance.band == band:
            dates_by_key.setdefault(appearance.show_key, appearance.show_date)
    return {position: dates_by_key[show_key].year for show_key, position in index.items()}


def _song_survival_rows(
    outcomes: list[SongSurvival],
    performance_counts: dict[str, int],
    catalog: dict[str, SongCatalogInfo],
    show_years: dict[int, int],
    computed_at: datetime,
) -> list[tuple]:
    rows = []
    for outcome in outcomes:
        info = catalog[outcome.song_key]
        rows.append(
            (
                outcome.band,
                info.song_title,
                info.reference_album,
                info.release_year,
                performance_counts[outcome.song_key],
                show_years[outcome.debut_index],
                show_years[outcome.last_index],
                outcome.duration_shows[SONG_MART_WINDOW],
                outcome.event[SONG_MART_WINDOW],
                outcome.returned_after_abandonment[SONG_MART_WINDOW],
                computed_at,
            )
        )
    return rows


def _curve_and_summary_rows(
    band: str, outcomes: list[SongSurvival], windows: tuple[int, ...], computed_at: datetime
) -> tuple[list[tuple], list[tuple]]:
    curve_rows: list[tuple] = []
    summary_rows: list[tuple] = []
    groups = group_by_album(outcomes)
    for album, group_outcomes in groups.items():
        for window in windows:
            points, summary = fit_curve(group_outcomes, window)
            for point in points:
                curve_rows.append(
                    (band, album, window, point.t_shows, point.at_risk, point.events,
                     point.survival_probability, point.ci_lower, point.ci_upper, computed_at)
                )
            summary_rows.append(
                (band, album, window, summary.songs, summary.events, summary.censored,
                 summary.median_survival_shows, computed_at)
            )
    return curve_rows, summary_rows


def compute_marts_from_data(
    appearances: list[ShowAppearance],
    performance_counts: dict[str, dict[str, int]],
    catalog: dict[str, dict[str, SongCatalogInfo]],
    computed_at: datetime,
    windows: tuple[int, ...] = WINDOWS,
) -> tuple[list[tuple], list[tuple], list[tuple]]:
    """Pure computation of every row of the three marts, from already-fetched
    data — no database access. Split out so it can be unit-tested directly,
    without mocking a connection."""
    song_rows: list[tuple] = []
    curve_rows: list[tuple] = []
    summary_rows: list[tuple] = []

    bands = sorted({a.band for a in appearances})
    for band in bands:
        outcomes = compute_survival(
            appearances, band, performance_counts.get(band, {}), catalog.get(band, {}), windows=windows
        )
        if not outcomes:
            continue
        show_years = _show_years_by_index(appearances, band)
        song_rows += _song_survival_rows(outcomes, performance_counts[band], catalog[band], show_years, computed_at)
        band_curve_rows, band_summary_rows = _curve_and_summary_rows(band, outcomes, windows, computed_at)
        curve_rows += band_curve_rows
        summary_rows += band_summary_rows

    return song_rows, curve_rows, summary_rows


def compute_all_marts(conn, computed_at: datetime | None = None) -> tuple[list[tuple], list[tuple], list[tuple]]:
    """Read the source data and compute every row of the three marts, without
    writing anything. Split out from `write_survival_marts` so the
    computation (which can be slow) and the transaction (which should be
    short) are separate."""
    computed_at = computed_at or datetime.now(timezone.utc)
    appearances = fetch_show_appearances(conn)
    performance_counts = fetch_performance_counts(conn)
    catalog = fetch_catalog(conn)
    return compute_marts_from_data(appearances, performance_counts, catalog, computed_at)


def write_survival_marts(conn, computed_at: datetime | None = None) -> tuple[int, int, int]:
    """Compute and replace the content of all three survival marts, in one
    transaction: if anything raises, the DELETEs are rolled back and the
    previous content (from the last successful run) is left untouched.

    Returns (song_rows, curve_rows, summary_rows) written.
    """
    ensure_tables(conn)
    song_rows, curve_rows, summary_rows = compute_all_marts(conn, computed_at)

    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM analytics.mart_song_survival")
            cur.execute("DELETE FROM analytics.mart_survival_curves")
            cur.execute("DELETE FROM analytics.mart_survival_summary")
            if song_rows:
                execute_values(
                    cur,
                    "INSERT INTO analytics.mart_song_survival (band, song_title, reference_album, release_year, "
                    "performances, debut_year, last_year, duration_shows_n50, event_n50, "
                    "returned_after_abandonment, computed_at) VALUES %s",
                    song_rows,
                )
            if curve_rows:
                execute_values(
                    cur,
                    "INSERT INTO analytics.mart_survival_curves (band, album, n_window, t_shows, at_risk, events, "
                    "survival_probability, ci_lower, ci_upper, computed_at) VALUES %s",
                    curve_rows,
                )
            if summary_rows:
                execute_values(
                    cur,
                    "INSERT INTO analytics.mart_survival_summary (band, album, n_window, songs, events, censored, "
                    "median_survival_shows, computed_at) VALUES %s",
                    summary_rows,
                )
    except Exception:
        # Leave the previous content in place rather than a half-deleted mart
        # (design decision D4): nothing here has been committed yet.
        conn.rollback()
        raise
    conn.commit()
    return len(song_rows), len(curve_rows), len(summary_rows)
