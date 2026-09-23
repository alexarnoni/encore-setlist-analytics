"""mart_tour_rotation against the oracle (spec-03 T4)."""

from fractions import Fraction

from tests.spec03.conftest import fetch
from tests.support import oracle


def _as_fraction(value, denom=10000):
    """The mart rounds to 4 decimals; compare against the oracle at the same precision."""
    return round(float(value), 4)


def test_mart_equals_the_oracle_for_every_tour(conn, shows):
    rows = fetch(
        conn,
        "select band, tour_name, first_year, last_year, shows, pairs, mean_jaccard, "
        "rotation, median_setlist_size, core_songs, distinct_songs from analytics.mart_tour_rotation",
    )
    got = {(b, t): (fy, ly, sh, pr, _as_fraction(mj), _as_fraction(rot), float(mss), cs, ds)
           for b, t, fy, ly, sh, pr, mj, rot, mss, cs, ds in rows}

    expected_stats = oracle.tour_rotation(shows)
    assert set(got) == set(expected_stats)

    for key, stats in expected_stats.items():
        fy, ly, sh, pr, mj, rot, mss, cs, ds = got[key]
        assert (fy, ly, sh, pr, cs, ds) == (
            stats.first_year, stats.last_year, stats.shows, stats.pairs,
            stats.core_songs, stats.distinct_songs,
        ), key
        assert abs(mj - float(stats.mean_jaccard)) < 1e-4, key
        assert abs(rot - float(stats.rotation)) < 1e-4, key
        assert abs(mss - float(stats.median_setlist_size)) < 1e-9, key


def test_short_tours_and_unknown_tour_are_absent(conn):
    rows = fetch(conn, "select band, tour_name from analytics.mart_tour_rotation")
    names = {t for _, t in rows}

    assert "Unknown tour" not in names
    assert ("Oasis", "Short Tour") not in set(rows)  # 4 shows, below the 5-show threshold


def test_metallica_m72_has_more_rotation_than_a_steady_tour(conn):
    rows = dict(
        fetch(conn, "select tour_name, rotation from analytics.mart_tour_rotation where band = 'Metallica'")
    )

    assert rows["M72 World Tour"] > rows["Steady Tour"]  # the spec's real-data sanity check, synthetic version
