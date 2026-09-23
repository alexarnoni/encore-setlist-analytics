"""The three survival marts, against the T1 oracle (spec-03 T8).

Uses `oracle.survival_outcomes`, an independent implementation of the
abandonment rule written before `encore.analysis.survival` existed (T1
predates T6), so agreement here is a real cross-check, not the production
code confirming itself.
"""

from tests.spec03.conftest import fetch
from tests.support import oracle


def test_song_survival_matches_the_oracle_at_window_50(conn, shows, catalog):
    rows = fetch(
        conn,
        "select band, song_title, performances, duration_shows_n50, event_n50, "
        "returned_after_abandonment from analytics.mart_song_survival",
    )
    got = {(band, title): (performances, duration, event, returned)
           for band, title, performances, duration, event, returned in rows}

    bands = {s.band for s in shows}
    assert bands  # sanity: the fixture actually has data

    for band in bands:
        expected = oracle.survival_outcomes(shows, band, catalog[band], window=50)
        expected_perf = oracle.performances(shows, band)

        mart_titles = {title for b, title in got if b == band}
        assert mart_titles == set(expected), band  # exactly the eligible songs, no more, no less

        for title, outcome in expected.items():
            performances, duration, event, returned = got[(band, title)]
            assert performances == expected_perf[title], (band, title)
            assert duration == outcome.duration, (band, title)
            assert event == outcome.event, (band, title)
            assert returned == outcome.returned, (band, title)


def test_song_survival_years_are_within_the_bands_show_history(conn, shows):
    rows = fetch(conn, "select band, debut_year, last_year from analytics.mart_song_survival")

    years_by_band: dict[str, tuple[int, int]] = {}
    for s in shows:
        if s.show_date is not None:
            lo, hi = years_by_band.get(s.band, (s.show_date.year, s.show_date.year))
            years_by_band[s.band] = (min(lo, s.show_date.year), max(hi, s.show_date.year))

    for band, debut_year, last_year in rows:
        band_lo, band_hi = years_by_band[band]
        assert band_lo <= debut_year <= last_year <= band_hi, (band, debut_year, last_year)


def test_survival_summary_matches_oracle_event_counts_at_every_window(conn, shows, catalog):
    rows = fetch(
        conn,
        "select band, n_window, songs, events, censored from analytics.mart_survival_summary where album = 'all'",
    )

    for band, window, songs, events, censored in rows:
        expected = oracle.survival_outcomes(shows, band, catalog[band], window=window)
        assert songs == len(expected), (band, window)
        assert events == sum(1 for o in expected.values() if o.event), (band, window)
        assert censored == songs - events, (band, window)


def test_survival_curves_are_well_formed(conn):
    """Bounds and monotonicity on the real, database-computed curves — the
    unit tests in test_survival_km.py check the same properties, but only on
    small hand-built data; this is the same check at real (synthetic) scale."""
    rows = fetch(
        conn,
        "select band, album, n_window, t_shows, survival_probability, ci_lower, ci_upper "
        "from analytics.mart_survival_curves order by band, album, n_window, t_shows",
    )
    assert rows

    previous_key = None
    previous_probability = None
    for band, album, window, t_shows, probability, ci_lower, ci_upper in rows:
        probability, ci_lower, ci_upper = float(probability), float(ci_lower), float(ci_upper)
        assert 0 <= probability <= 1, (band, album, window, t_shows)
        assert ci_lower <= probability <= ci_upper, (band, album, window, t_shows)
        assert 0 <= ci_lower and ci_upper <= 1, (band, album, window, t_shows)

        key = (band, album, window)
        if key == previous_key:
            assert probability <= previous_probability + 1e-9, key  # non-increasing within one curve
        previous_key, previous_probability = key, probability
