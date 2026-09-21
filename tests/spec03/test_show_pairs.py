"""int_show_pairs against the oracle (spec-03 T3)."""

from fractions import Fraction

from tests.spec03.conftest import fetch
from tests.support import oracle


def test_pairs_equal_the_oracle(conn, shows):
    rows = fetch(
        conn,
        "select band, tour_name, first_show_key, second_show_key, second_show_date, "
        "intersection_size, union_size, jaccard from intermediate.int_show_pairs",
    )
    got = {(r[2], r[3]): (r[0], r[1], r[4], Fraction(r[5], r[6])) for r in rows}
    expected = {(p.first_id, p.second_id): (p.band, p.tour, p.second_date, p.jaccard)
                for p in oracle.consecutive_pairs(shows)}

    assert got == expected


def test_jaccard_column_is_intersection_over_union(conn):
    rows = fetch(conn, "select intersection_size, union_size, jaccard from intermediate.int_show_pairs")

    assert rows
    for intersection, union, jaccard in rows:
        assert abs(float(jaccard) - intersection / union) < 1e-9
        assert 0 <= jaccard <= 1


def test_unknown_tour_shows_are_never_paired(conn):
    rows = fetch(conn, "select count(*) from intermediate.int_show_pairs where tour_name = 'Unknown tour'")

    assert rows[0][0] == 0
