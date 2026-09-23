"""Unit tests for the survival I/O layer (spec-03 T8): the pure computation
(no database) gets the bulk of the coverage; the fetch/write functions are
checked against a mocked connection, the same style as tests/test_ops.py.
"""

from datetime import date, datetime, timezone
from unittest.mock import MagicMock

import pytest

from encore.analysis import io as survival_io
from encore.analysis.survival import ShowAppearance, SongCatalogInfo

BAND = "TestBand"
NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _cursor(conn) -> MagicMock:
    return conn.cursor.return_value.__enter__.return_value


def _weekly_appearances(band: str, song_show_pairs: list[tuple[str, int]], total_shows: int) -> list[ShowAppearance]:
    """A filler song at every show plus the given (song, show_index) pairs,
    on distinct weekly dates starting 2000-01-01."""
    dates = [date(2000, 1, 1).toordinal() + 7 * i for i in range(total_shows)]
    dates = [date.fromordinal(d) for d in dates]
    appearances = [ShowAppearance(band, "Filler", f"s{i}", dates[i - 1]) for i in range(1, total_shows + 1)]
    appearances += [ShowAppearance(band, song, f"s{i}", dates[i - 1]) for song, i in song_show_pairs]
    return appearances


# --- fetch_* against a mocked connection ------------------------------------


def test_fetch_show_appearances_builds_dataclasses_from_rows():
    conn = MagicMock()
    d = date(2020, 5, 1)
    _cursor(conn).fetchall.return_value = [("Oasis", "wonderwall", "s1", d)]

    result = survival_io.fetch_show_appearances(conn)

    assert result == [ShowAppearance("Oasis", "wonderwall", "s1", d)]
    assert "int_show_song_sets" in _cursor(conn).execute.call_args[0][0]


def test_fetch_performance_counts_groups_by_band():
    conn = MagicMock()
    _cursor(conn).fetchall.return_value = [("Oasis", "wonderwall", 900), ("Muse", "starlight", 400)]

    result = survival_io.fetch_performance_counts(conn)

    assert result == {"Oasis": {"wonderwall": 900}, "Muse": {"starlight": 400}}
    executed = _cursor(conn).execute.call_args[0][0]
    assert "is_matched" in executed and "show_year IS NOT NULL" in executed


def test_fetch_catalog_groups_by_band():
    conn = MagicMock()
    _cursor(conn).fetchall.return_value = [("Oasis", "wonderwall", "Wonderwall", "(What's the Story)...", 1995)]

    result = survival_io.fetch_catalog(conn)

    assert result == {"Oasis": {"wonderwall": SongCatalogInfo("Wonderwall", "(What's the Story)...", 1995)}}


def test_ensure_tables_creates_all_three_marts_and_commits():
    conn = MagicMock()

    survival_io.ensure_tables(conn)

    executed = [c.args[0] for c in _cursor(conn).execute.call_args_list]
    assert any("mart_song_survival" in sql for sql in executed)
    assert any("mart_survival_curves" in sql for sql in executed)
    assert any("mart_survival_summary" in sql for sql in executed)
    assert all("CREATE TABLE IF NOT EXISTS" in sql for sql in executed)
    conn.commit.assert_called_once()


# --- pure computation: compute_marts_from_data ------------------------------


def test_song_survival_rows_have_the_right_shape_and_n50_window():
    # A song eligible (matched to an album), played weeks 1-3 then abandoned
    # (window 50 has plenty of silent shows after week 3 in a 60-show history).
    appearances = _weekly_appearances(BAND, [("X", 1), ("X", 2), ("X", 3)], total_shows=60)
    performance_counts = {BAND: {"Filler": 60, "X": 3}}
    catalog = {BAND: {
        "Filler": SongCatalogInfo("Filler", "Album", 1990),
        "X": SongCatalogInfo("Song X", "Album", 2000),
    }}

    song_rows, curve_rows, summary_rows = survival_io.compute_marts_from_data(
        appearances, performance_counts, catalog, NOW
    )

    row = next(r for r in song_rows if r[1] == "Song X")
    band, song_title, reference_album, release_year, performances_n, debut_year, last_year, \
        duration_n50, event_n50, returned, computed_at = row
    assert (band, song_title, reference_album, release_year) == (BAND, "Song X", "Album", 2000)
    assert performances_n == 3
    assert debut_year == 2000  # week 1 of 2000-01-01
    assert last_year == 2000  # week 3, still January 2000
    assert (duration_n50, event_n50, returned) == (3, True, False)
    assert computed_at is NOW
    assert curve_rows and summary_rows  # sanity: the other two marts got something too


def test_song_mart_uses_window_50_specifically_not_some_other_window():
    # 40 shows, song played 1,2,3 then never again. At window 25 that is a
    # clean abandonment (37 silent shows follow); at window 50 there aren't
    # even 50 shows left in the whole history, so it's censored instead. If
    # the mart read the wrong window's dict, this discriminates it.
    appearances = _weekly_appearances(BAND, [("X", 1), ("X", 2), ("X", 3)], total_shows=40)
    performance_counts = {BAND: {"Filler": 40, "X": 3}}
    catalog = {BAND: {"Filler": SongCatalogInfo("Filler", "Album", 1990), "X": SongCatalogInfo("Song X", "Album", 2000)}}

    song_rows, _, _ = survival_io.compute_marts_from_data(appearances, performance_counts, catalog, NOW)

    _, _, _, _, _, _, _, duration_n50, event_n50, _, _ = next(r for r in song_rows if r[1] == "Song X")
    assert (duration_n50, event_n50) == (40, False)  # censored at window 50, NOT abandoned as at window 25


def test_debut_and_last_year_come_from_the_real_show_dates_not_the_index():
    # Debut in year 2000, last (censored) appearance far enough along to land
    # in year 2001 given weekly shows.
    appearances = _weekly_appearances(BAND, [("X", 1), ("X", 30), ("X", 55)], total_shows=55)
    performance_counts = {BAND: {"Filler": 55, "X": 3}}
    catalog = {BAND: {"Filler": SongCatalogInfo("Filler", "Album", 1990), "X": SongCatalogInfo("Song X", "Album", 2000)}}

    song_rows, _, _ = survival_io.compute_marts_from_data(appearances, performance_counts, catalog, NOW)

    _, _, _, _, _, debut_year, last_year, *_ = next(r for r in song_rows if r[1] == "Song X")
    assert debut_year == 2000
    assert last_year == 2001  # week 55 (~ 385 days later) has rolled into the next year


def test_curves_include_all_group_and_per_album_groups_including_non_album():
    appearances = _weekly_appearances(
        BAND, [("Alpha", 1), ("Alpha", 2), ("Alpha", 3), ("Beta", 1), ("Beta", 2), ("Beta", 3)], total_shows=60
    )
    performance_counts = {BAND: {"Filler": 60, "Alpha": 3, "Beta": 3}}
    catalog = {BAND: {
        "Filler": SongCatalogInfo("Filler", "Album", 1990),
        "Alpha": SongCatalogInfo("Alpha", "Album", 2000),  # on a studio album
        "Beta": SongCatalogInfo("Beta", None, 2001),  # recording-only, dated: "non-album"
    }}

    _, curve_rows, summary_rows = survival_io.compute_marts_from_data(appearances, performance_counts, catalog, NOW)

    albums = {row[1] for row in summary_rows if row[0] == BAND}
    assert albums == {"all", "Album", "non-album"}
    # every summary row's window is one of the module's windows
    assert {row[2] for row in summary_rows} <= {25, 50, 100}
    # curve rows exist for at least the "all" group
    assert any(row[1] == "all" for row in curve_rows)


def test_a_band_with_no_eligible_songs_produces_no_rows():
    appearances = _weekly_appearances(BAND, [], total_shows=10)  # only "Filler", but never enough performances below
    performance_counts = {BAND: {"Filler": 2}}  # below MIN_PERFORMANCES
    catalog = {BAND: {"Filler": SongCatalogInfo("Filler", "Album", 1990)}}

    song_rows, curve_rows, summary_rows = survival_io.compute_marts_from_data(
        appearances, performance_counts, catalog, NOW
    )

    assert (song_rows, curve_rows, summary_rows) == ([], [], [])


def test_multiple_bands_are_kept_separate():
    a = _weekly_appearances("Oasis", [("X", 1), ("X", 2), ("X", 3)], total_shows=60)
    b = _weekly_appearances("Muse", [("Y", 1), ("Y", 2), ("Y", 3)], total_shows=60)
    performance_counts = {"Oasis": {"Filler": 60, "X": 3}, "Muse": {"Filler": 60, "Y": 3}}
    catalog = {
        "Oasis": {"Filler": SongCatalogInfo("Filler", "A", 1990), "X": SongCatalogInfo("X", "A", 2000)},
        "Muse": {"Filler": SongCatalogInfo("Filler", "B", 1990), "Y": SongCatalogInfo("Y", "B", 2001)},
    }

    song_rows, _, _ = survival_io.compute_marts_from_data(a + b, performance_counts, catalog, NOW)

    bands = {row[0] for row in song_rows}
    assert bands == {"Oasis", "Muse"}


# --- write_survival_marts: transaction behaviour ----------------------------


def test_write_survival_marts_deletes_inserts_and_commits(monkeypatch):
    conn = MagicMock()
    monkeypatch.setattr(survival_io, "ensure_tables", lambda conn: None)  # its own commit is tested separately
    monkeypatch.setattr(survival_io, "compute_all_marts", lambda conn, computed_at=None: ([("row",)], [], []))
    monkeypatch.setattr(survival_io, "execute_values", lambda cur, sql, rows: cur.execute(sql))

    result = survival_io.write_survival_marts(conn)

    assert result == (1, 0, 0)
    executed = [c.args[0] for c in _cursor(conn).execute.call_args_list]
    assert any("DELETE FROM analytics.mart_song_survival" in sql for sql in executed)
    assert any("DELETE FROM analytics.mart_survival_curves" in sql for sql in executed)
    assert any("DELETE FROM analytics.mart_survival_summary" in sql for sql in executed)
    conn.commit.assert_called_once()
    conn.rollback.assert_not_called()


def test_write_survival_marts_rolls_back_and_reraises_on_failure(monkeypatch):
    conn = MagicMock()
    monkeypatch.setattr(survival_io, "ensure_tables", lambda conn: None)
    monkeypatch.setattr(survival_io, "compute_all_marts", lambda conn, computed_at=None: ([("row",)], [], []))
    monkeypatch.setattr(survival_io, "execute_values", lambda cur, sql, rows: cur.execute(sql))
    _cursor(conn).execute.side_effect = [None, None, None, RuntimeError("boom")]

    with pytest.raises(RuntimeError, match="boom"):
        survival_io.write_survival_marts(conn)

    conn.rollback.assert_called_once()
    conn.commit.assert_not_called()


def test_write_survival_marts_skips_empty_inserts(monkeypatch):
    conn = MagicMock()
    monkeypatch.setattr(survival_io, "ensure_tables", lambda conn: None)
    monkeypatch.setattr(survival_io, "compute_all_marts", lambda conn, computed_at=None: ([], [], []))

    result = survival_io.write_survival_marts(conn)

    assert result == (0, 0, 0)
    executed = [c.args[0] for c in _cursor(conn).execute.call_args_list]
    assert not any("INSERT" in sql for sql in executed)  # only the three DELETEs
    conn.commit.assert_called_once()
