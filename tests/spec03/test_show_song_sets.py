"""int_show_song_sets against the oracle (spec-03 T2)."""

from collections import defaultdict

from tests.spec03.conftest import fetch
from tests.support import oracle


def test_every_show_set_equals_the_oracle(conn, shows):
    rows = fetch(conn, "select show_key, band, tour_name, show_date, song_title from intermediate.int_show_song_sets")
    got: dict[str, set[str]] = defaultdict(set)
    meta: dict[str, tuple] = {}
    for show_key, band, tour, show_date, title in rows:
        got[show_key].add(title)
        meta[show_key] = (band, tour, show_date)

    expected = oracle.show_sets(shows)
    assert {k: frozenset(v) for k, v in got.items()} == expected
    assert len(rows) == sum(len(v) for v in expected.values())  # one row per show and song, no duplicates

    by_id = {s.setlist_id: s for s in shows}
    for show_key, (band, tour, show_date) in meta.items():
        show = by_id[show_key]
        assert (band, tour, show_date) == (show.band, oracle.tour_of(show), show.show_date)


def test_excluded_shows_and_entries_are_absent(conn, shows):
    keys = {r[0] for r in fetch(conn, "select distinct show_key from intermediate.int_show_song_sets")}

    assert not any(s.setlist_id in keys for s in shows if s.show_date is None)  # undated
    names = {r[0] for r in fetch(conn, "select distinct song_title from intermediate.int_show_song_sets")}
    assert not any(n.startswith("Zzz Unmatched") for n in names)  # unmatched titles
    assert "Synthetic Cover" not in names and "Intro Tape" not in names  # covers and tape
