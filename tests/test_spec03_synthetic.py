"""Checks that the synthetic histories and the oracle behave as designed.

The expected numbers here are derived by hand (see the comments), so a bug in
the oracle or in a builder shows up before either is used to judge the dbt
models or the survival module.
"""

from fractions import Fraction

import pytest

from tests.support import db as spec03_db
from tests.support import histories as h
from tests.support import oracle as o


@pytest.fixture(scope="module")
def pool():
    return h.SongPool(
        album=tuple(f"Album Song {i:02d}" for i in range(80)),
        recording_with_year=tuple(f"Rec Year {i:02d}" for i in range(5)),
        recording_no_year=tuple(f"Rec NoYear {i:02d}" for i in range(5)),
    )


@pytest.fixture(scope="module")
def catalog(pool):
    info = {name: o.CatalogInfo("Some Album", 2000) for name in pool.album}
    info.update({name: o.CatalogInfo(None, 2001) for name in pool.recording_with_year})
    info.update({name: o.CatalogInfo(None, None) for name in pool.recording_no_year})
    return info


def _pools(pool):
    return {b: pool for b in ("Oasis", "Metallica", "Muse", "Arctic Monkeys", "Linkin Park")}


# --- builders ---------------------------------------------------------------

def test_histories_are_deterministic_with_unique_ids(pool):
    first, second = h.all_histories(_pools(pool)), h.all_histories(_pools(pool))

    assert first == second
    ids = [s.setlist_id for s in first]
    assert len(ids) == len(set(ids))


def test_show_counts_per_band(pool):
    shows = h.all_histories(_pools(pool))
    per_band = {b: sum(1 for s in shows if s.band == b) for b in {s.band for s in shows}}

    assert per_band == {"Oasis": 55, "Metallica": 36, "Muse": 260, "Arctic Monkeys": 41, "Linkin Park": 150}
    assert sum(1 for s in shows if s.show_date is None) == 3  # 2 Oasis, 1 Arctic Monkeys


def test_unmatched_titles_never_appear_among_matched_songs(pool):
    for s in h.all_histories(_pools(pool)):
        assert not any(name.startswith(h.UNMATCHED_PREFIX) for name in s.songs)
        assert all(name.startswith(h.UNMATCHED_PREFIX) for name in s.unmatched)


def test_a_pool_that_is_too_small_is_refused():
    with pytest.raises(ValueError):
        h.oasis_rotation_history(h.SongPool(album=("only one",)))


# --- rotation oracle, against hand-computed values ---------------------------

def test_oracle_jaccard():
    assert o.jaccard(frozenset("abc"), frozenset("abc")) == 1
    assert o.jaccard(frozenset("ab"), frozenset("cd")) == 0
    assert o.jaccard(frozenset("abc"), frozenset("abd")) == Fraction(1, 2)  # 2 / 4


def test_oasis_tours(pool):
    stats = o.tour_rotation(h.oasis_rotation_history(pool))

    # Short Tour (4 shows) and the no-tour shows are excluded.
    assert set(stats) == {("Oasis", "Fixed Tour"), ("Oasis", "Alternating Tour"), ("Oasis", "Overlap Tour"),
                          ("Oasis", "Reverse Tour")}

    fixed = stats[("Oasis", "Fixed Tour")]  # 20 dated shows (2 undated ignored), same 15 songs
    assert (fixed.shows, fixed.pairs, fixed.rotation) == (20, 19, 0)
    assert (fixed.core_songs, fixed.distinct_songs, fixed.median_setlist_size) == (15, 15, 15)

    alternating = stats[("Oasis", "Alternating Tour")]  # two disjoint sets of 10
    assert (alternating.shows, alternating.pairs, alternating.rotation) == (12, 11, 1)
    assert (alternating.core_songs, alternating.distinct_songs, alternating.median_setlist_size) == (0, 20, 10)

    overlap = stats[("Oasis", "Overlap Tour")]
    # pairs: 3/5, 1/3, 1, 1/7 -> sum 218/105, mean 109/210, rotation 101/210
    assert overlap.pairs == 4
    assert overlap.mean_jaccard == Fraction(109, 210) and overlap.rotation == Fraction(101, 210)
    assert (overlap.core_songs, overlap.distinct_songs, overlap.median_setlist_size) == (1, 10, 4)
    assert (overlap.first_year, overlap.last_year) == (2002, 2002)


def test_same_date_shows_are_ordered_by_setlist_id(pool):
    pairs = [p for p in o.consecutive_pairs(h.oasis_rotation_history(pool)) if p.tour == "Overlap Tour"]

    assert [(p.first_id, p.second_id) for p in pairs] == [
        ("oa-o-001", "oa-o-002"), ("oa-o-002", "oa-o-003"), ("oa-o-003", "oa-o-004"), ("oa-o-004", "oa-o-005"),
    ]


def test_reverse_tour_is_paired_by_date_not_by_id(pool):
    pairs = [p for p in o.consecutive_pairs(h.oasis_rotation_history(pool)) if p.tour == "Reverse Tour"]

    # dates ascend from oa-r-006 to oa-r-001, so that is the order of the pairs
    assert [(p.first_id, p.second_id) for p in pairs] == [
        ("oa-r-006", "oa-r-005"), ("oa-r-005", "oa-r-004"), ("oa-r-004", "oa-r-003"),
        ("oa-r-003", "oa-r-002"), ("oa-r-002", "oa-r-001"),
    ]
    # sets {0,1,2} {0,1,3} {0,4,5} {0,4,5} {1,2,3} {0,1,2}: 2/4, 1/5, 1, 0 (disjoint), 2/4
    assert [p.jaccard for p in pairs] == [Fraction(1, 2), Fraction(1, 5), 1, 0, Fraction(1, 2)]


def test_metallica_tours_and_years(pool):
    shows = h.metallica_m72_history(pool)
    stats = o.tour_rotation(shows)

    m72 = stats[("Metallica", "M72 World Tour")]  # sets share 5 of 25 songs: Jaccard 1/5
    assert (m72.shows, m72.pairs, m72.mean_jaccard, m72.rotation) == (30, 29, Fraction(1, 5), Fraction(4, 5))
    # the 5 songs common to both sets are in every show: they are the core
    assert (m72.core_songs, m72.distinct_songs, m72.median_setlist_size) == (5, 25, 15)
    assert (m72.first_year, m72.last_year) == (2022, 2023)

    steady = stats[("Metallica", "Steady Tour")]
    assert (steady.shows, steady.pairs, steady.rotation, steady.core_songs) == (6, 5, 0, 10)

    # A pair belongs to the year of its SECOND show: 10 M72 pairs end in 2022,
    # 19 in 2023; the steady tour adds 5 pairs with Jaccard 1 to 2023.
    by_year = o.band_rotation_by_year(shows)
    assert by_year[("Metallica", 2022)] == o.YearStats(10, Fraction(1, 5), Fraction(4, 5))
    assert by_year[("Metallica", 2023)].pairs == 24
    assert by_year[("Metallica", 2023)].mean_jaccard == Fraction(11, 30)


def test_undated_and_unmatched_only_shows_do_not_count(pool):
    shows = h.oasis_rotation_history(pool)

    assert "oa-f-u1" not in o.show_sets(shows)
    assert len(o.show_sets(shows)) == 53


# --- survival oracle, against hand-derived outcomes ---------------------------

def test_muse_show_index_is_continuous_across_the_hiatus(pool):
    shows = h.muse_survival_history(pool)
    index = o.band_show_index(shows, "Muse")

    assert len(index) == h.MUSE_TOTAL_SHOWS
    assert index["mu-130"] == 130 and index["mu-131"] == 131
    gap_days = (shows[130].show_date - shows[129].show_date).days
    assert gap_days > 4000  # about 12 calendar years, but adjacent in the show index


def test_muse_eligible_songs(pool, catalog):
    plan = h.muse_plan(pool)
    eligible = set(o.eligible_songs(h.muse_survival_history(pool), "Muse", catalog))

    expected = {plan[k][0] for k in ("filler", "exact", "short", "censored", "returns",
                                     "returns_and_stays", "hiatus", "recording_with_year")}
    assert eligible == expected
    assert plan["two_performances"][0] not in eligible  # 2 performances
    assert plan["recording_no_year"][0] not in eligible  # recording-only, no release year


# (duration, event, returned, gaps) per song and window, derived by hand from
# the plan in muse_plan(): 260 shows, appearances as listed there.
MUSE_EXPECTED = {
    25: {"filler": (260, False, False, 0), "exact": (56, True, True, 1), "short": (55, True, True, 1),
         "censored": (131, True, False, 0), "returns": (78, True, True, 1),
         "returns_and_stays": (250, False, True, 2), "hiatus": (10, True, False, 0),
         "recording_with_year": (4, True, False, 0)},
    50: {"filler": (260, False, False, 0), "exact": (56, True, True, 1), "short": (55, True, False, 0),
         "censored": (161, False, False, 0), "returns": (78, True, True, 1),
         "returns_and_stays": (250, False, True, 2), "hiatus": (10, True, False, 0),
         "recording_with_year": (4, True, False, 0)},
    100: {"filler": (260, False, False, 0), "exact": (56, True, False, 0), "short": (55, True, False, 0),
          "censored": (161, False, False, 0), "returns": (78, True, False, 0),
          "returns_and_stays": (250, False, True, 1), "hiatus": (10, True, False, 0),
          "recording_with_year": (4, True, False, 0)},
}


@pytest.mark.parametrize("window", [25, 50, 100])
def test_muse_survival_outcomes(pool, catalog, window):
    plan = h.muse_plan(pool)
    outcomes = o.survival_outcomes(h.muse_survival_history(pool), "Muse", catalog, window)

    got = {key: (outcomes[name].duration, outcomes[name].event, outcomes[name].returned, outcomes[name].gaps)
           for key, (name, _) in plan.items() if name in outcomes}
    assert got == MUSE_EXPECTED[window]


def test_gap_of_exactly_the_window_is_a_gap_one_show_less_is_not():
    # appearances at 1 and 4: 2 silent shows in between.
    reached = o.outcome([1, 4], 10, window=2)
    assert (reached.gaps, reached.returned) == (1, True)
    short = o.outcome([1, 4], 10, window=3)
    assert (short.gaps, short.returned) == (0, False)
    assert short.event and short.duration == 4  # the final gap (6 shows) is a full 3-show gap


def test_a_song_that_returns_and_is_still_played_is_censored():
    out = o.outcome([1, 8, 9, 10], 11, window=5)

    assert out == o.Outcome(1, 10, 10, False, True, 1)


def test_a_song_that_returns_and_then_leaves_is_an_event():
    out = o.outcome([1, 2, 3, 9], 20, window=5)

    assert out == o.Outcome(1, 9, 9, True, True, 1)


def test_a_song_played_once_has_duration_one():
    # played once at show 7 of 100 and never again for the next 50 shows: abandoned, duration 1
    assert o.outcome([7], 100, window=50) == o.Outcome(7, 7, 1, True, False, 0)
    # played once at show 70 of 100: fewer than 50 shows remain, so it is censored (100 - 70 + 1)
    assert o.outcome([70], 100, window=50) == o.Outcome(70, 70, 31, False, False, 0)


def test_arctic_eligibility(pool, catalog):
    a, rw, rn = pool.album, pool.recording_with_year, pool.recording_no_year
    shows = h.arctic_eligibility_history(pool)

    perf = o.performances(shows, "Arctic Monkeys")
    assert perf[a[3]] == 2  # 3 plays, one in an undated show
    assert perf[a[4]] == 3  # twice in one show
    apps, _ = o.appearances(shows, "Arctic Monkeys")
    assert len(apps[a[4]]) == 2  # ... but only 2 distinct shows

    eligible = set(o.eligible_songs(shows, "Arctic Monkeys", catalog))
    assert eligible == {a[0], a[1], a[4], rw[0]}
    assert {a[2], a[3], rw[1], rn[0]}.isdisjoint(eligible)


def test_linkin_random_history_shape(pool):
    shows = h.linkin_random_history(pool)
    tours = {}
    for s in shows:
        tours[s.tour_name] = tours.get(s.tour_name, 0) + 1

    assert tours == {"LP Tour 1": 50, "LP Tour 2": 50, None: 20, "LP Tour 3": 30}
    assert all(s.songs for s in shows)
    assert h.linkin_random_history(pool, seed=8) != shows  # the seed matters


# --- the guard that keeps these tools away from the real database -----------

@pytest.mark.parametrize("host,port,allowed", [
    ("spec03-postgres", "5432", True),
    ("localhost", "5446", True),
    ("127.0.0.1", "5446", True),
    ("postgres", "5432", False),      # the real service, from inside a container
    ("localhost", "5435", False),     # the real published port
    ("", "5432", False),
])
def test_only_the_spec03_database_is_allowed(monkeypatch, host, port, allowed):
    monkeypatch.setenv("POSTGRES_HOST", host)
    monkeypatch.setenv("POSTGRES_PORT", port)

    if allowed:
        spec03_db.assert_spec03_database()
    else:
        with pytest.raises(RuntimeError, match="refusing"):
            spec03_db.assert_spec03_database()
