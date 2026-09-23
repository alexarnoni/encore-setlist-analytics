"""mart_band_rotation_by_year against the oracle (spec-03 T5)."""

from tests.spec03.conftest import fetch
from tests.support import oracle


def test_mart_equals_the_oracle(conn, shows):
    rows = fetch(conn, "select band, show_year, pairs, mean_jaccard, rotation from analytics.mart_band_rotation_by_year")
    got = {(b, y): (p, round(float(mj), 4), round(float(r), 4)) for b, y, p, mj, r in rows}

    expected = oracle.band_rotation_by_year(shows)
    assert set(got) == set(expected)
    for key, stats in expected.items():
        pairs, mean_jaccard, rotation = got[key]
        assert pairs == stats.pairs, key
        assert abs(mean_jaccard - float(stats.mean_jaccard)) < 1e-4, key
        assert abs(rotation - float(stats.rotation)) < 1e-4, key


def test_metallica_pair_crossing_new_year_counts_for_its_second_show(conn):
    # M72-like tour starts 2022-12-01 (decision Q3: a pair belongs to the
    # year of its SECOND show), so 2022 has 10 pairs and 2023 has 24
    # (19 from M72 + 5 from the Steady Tour) — matches the T4/oracle numbers.
    rows = dict(
        (y, p) for y, p in fetch(conn, "select show_year, pairs from analytics.mart_band_rotation_by_year where band = 'Metallica'")
    )

    assert rows[2022] == 10
    assert rows[2023] == 24
