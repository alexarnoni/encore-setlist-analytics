"""Deterministic synthetic setlist histories for spec 03 (rotation and survival).

Nothing here is setlist.fm data: the shows are invented, and each scenario is
built so that its answer is known by construction (a tour that repeats one set
has rotation 0, two alternating disjoint sets give rotation 1, a song absent for
exactly the window is abandoned, and so on). The same builders feed

* the unit tests (with a fake `SongPool`), and
* `scripts/spec03/load_synthetic.py`, which loads them into `raw_setlistfm` of
  the disposable spec-03 database (with a pool of real catalog song names, so
  the songs match the real MusicBrainz catalog), where dbt models and the
  survival module are checked against `tests/support/oracle.py`.

Song names must reach the catalog untouched, so they come from a pool; names
that must NOT match start with "Zzz Unmatched".
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, timedelta

UNMATCHED_PREFIX = "Zzz Unmatched"


@dataclass(frozen=True)
class SongPool:
    """Catalog song names of one band, by how they enter the catalog."""

    album: tuple[str, ...]  # on a studio album (has a reference album and a year)
    recording_with_year: tuple[str, ...] = ()  # recording-only, dated
    recording_no_year: tuple[str, ...] = ()  # recording-only, no release year


@dataclass(frozen=True)
class SyntheticShow:
    setlist_id: str
    band: str
    show_date: date | None  # None = a show whose date cannot be parsed
    tour_name: str | None  # None = no tour on setlist.fm ("Unknown tour")
    songs: tuple[str, ...]  # matched catalog songs in playing order (may repeat)
    unmatched: tuple[str, ...] = ()  # titles that are not in the catalog
    covers: tuple[str, ...] = ()
    tape: tuple[str, ...] = ()


def _need(pool: SongPool, n: int) -> None:
    if len(pool.album) < n:
        raise ValueError(f"song pool has {len(pool.album)} album songs, {n} needed")


def _extras(band: str, i: int) -> dict:
    """Every 5th show also has an unmatched title, a cover and a tape entry:
    none of them may reach a setlist set."""
    if i % 5:
        return {}
    return {
        "unmatched": (f"{UNMATCHED_PREFIX} {band} {i}",),
        "covers": ("Synthetic Cover",),
        "tape": ("Intro Tape",),
    }


def _run(prefix: str, band: str, tour: str | None, start: date, step_days: int,
         sets: list[tuple[str, ...]]) -> list[SyntheticShow]:
    return [
        SyntheticShow(
            setlist_id=f"{prefix}-{i:03d}",
            band=band,
            show_date=start + timedelta(days=step_days * (i - 1)),
            tour_name=tour,
            songs=songs,
            **_extras(band, i),
        )
        for i, songs in enumerate(sets, start=1)
    ]


# --- Oasis: rotation basics -------------------------------------------------

def oasis_rotation_history(pool: SongPool) -> list[SyntheticShow]:
    """Tours with known rotation:

    * "Fixed Tour": 20 shows, the same 15 songs (rotation 0, 15 core songs),
      plus two undated shows that must be ignored and one repeated song;
    * "Alternating Tour": 12 shows alternating two disjoint sets of 10
      (every consecutive pair has Jaccard 0, rotation 1);
    * "Overlap Tour": 5 hand-picked sets (two shows share a date);
    * "Short Tour": 4 shows (excluded from rotation: fewer than 5);
    * "Reverse Tour": 6 shows whose setlist ids DESCEND while the dates ascend,
      so ordering by id instead of by date gives different pairs;
    * no tour: 6 shows ("Unknown tour": excluded from pairs, but part of the
      band's show history).
    """
    _need(pool, 60)
    a = pool.album
    band = "Oasis"

    fixed = tuple(a[0:15])
    fixed_sets = [fixed[k % 15:] + fixed[: k % 15] for k in range(20)]  # rotated order
    fixed_sets[2] = fixed_sets[2] + (fixed[0],)  # a song played twice in one show
    shows = _run("oa-f", band, "Fixed Tour", date(2000, 3, 1), 2, fixed_sets)
    shows += [
        SyntheticShow("oa-f-u1", band, None, "Fixed Tour", fixed[:5]),
        SyntheticShow("oa-f-u2", band, None, "Fixed Tour", fixed[:5]),
    ]

    sa, sb = tuple(a[15:25]), tuple(a[25:35])
    shows += _run("oa-a", band, "Alternating Tour", date(2001, 5, 1), 3,
                  [sa if i % 2 == 0 else sb for i in range(12)])

    p = a[35:45]
    overlap = [
        (p[0], p[1], p[2], p[3]),
        (p[0], p[1], p[2], p[4]),
        (p[0], p[1], p[5], p[6]),
        (p[0], p[1], p[5], p[6]),
        (p[7], p[8], p[9], p[0]),
    ]
    dates = [date(2002, 7, 1), date(2002, 7, 2), date(2002, 7, 2), date(2002, 7, 4), date(2002, 7, 5)]
    for i, (songs, d) in enumerate(zip(overlap, dates), start=1):
        shows.append(SyntheticShow(f"oa-o-{i:03d}", band, d, "Overlap Tour", songs))

    shows += _run("oa-s", band, "Short Tour", date(2003, 2, 1), 2, [tuple(a[45:50])] * 4)

    reverse_sets = [(a[0], a[1], a[2]), (a[0], a[1], a[3]), (a[0], a[4], a[5]),
                    (a[0], a[4], a[5]), (a[1], a[2], a[3]), (a[0], a[1], a[2])]
    for i, songs in enumerate(reverse_sets, start=1):
        shows.append(SyntheticShow(f"oa-r-{7 - i:03d}", band, date(2004, 9, 1) + timedelta(days=i),
                                   "Reverse Tour", songs))

    unknown_sets = [tuple(a[50:53]), tuple(a[52:55]), tuple(a[54:57]),
                    tuple(a[56:59]), tuple(a[50:52]), tuple(a[58:60])]
    shows += _run("oa-x", band, None, date(1999, 4, 1), 5, unknown_sets)
    return shows


# --- Metallica: two different sets per city, across a year boundary ----------

def metallica_m72_history(pool: SongPool) -> list[SyntheticShow]:
    """"M72 World Tour": 30 shows alternating set X and set Y (5 songs in
    common, 25 in the union, so every pair has Jaccard 0.2 and the tour has
    rotation 0.8), starting 2022-12-01 every 3 days so the tour crosses New
    Year. "Steady Tour": 6 identical shows in 2023 (rotation 0)."""
    _need(pool, 40)
    a = pool.album
    band = "Metallica"
    x, y = tuple(a[0:15]), tuple(a[10:25])
    shows = _run("me-m", band, "M72 World Tour", date(2022, 12, 1), 3,
                 [x if i % 2 == 0 else y for i in range(30)])
    shows += _run("me-s", band, "Steady Tour", date(2023, 3, 1), 2, [tuple(a[30:40])] * 6)
    return shows


# --- Muse: survival mechanics -----------------------------------------------

MUSE_TOTAL_SHOWS = 260


def muse_plan(pool: SongPool) -> dict[str, tuple[str, set[int]]]:
    """Song name and the show indices (1-based) where it is played."""
    _need(pool, 10)
    if not pool.recording_with_year or not pool.recording_no_year:
        raise ValueError("Muse plan needs recording-only songs with and without a year")
    a = pool.album
    return {
        "filler": (a[0], set(range(1, MUSE_TOTAL_SHOWS + 1))),  # every show
        "exact": (a[1], {1, 2, 3, 54, 55, 56}),  # gap of exactly 50 after show 3
        "short": (a[2], {1, 2, 3, 53, 54, 55}),  # gap of 49 after show 3
        "censored": (a[3], set(range(100, 231, 10))),  # played every 10th show, 30 shows before the end
        "returns": (a[4], {5, 6, 7, 80, 81, 82}),  # leaves, comes back, then leaves for good
        "returns_and_stays": (a[7], {8, 9, 10, 100, 101, 102, 255, 256, 257}),  # two gaps, still played at the end
        "hiatus": (a[5], set(range(126, 136))),  # played across the 12-year hiatus
        "two_performances": (a[6], {10, 200}),  # fewer than 3 performances
        "recording_with_year": (pool.recording_with_year[0], {20, 21, 22, 23}),
        "recording_no_year": (pool.recording_no_year[0], {30, 31, 32, 33}),
    }


def muse_survival_history(pool: SongPool) -> list[SyntheticShow]:
    """260 shows; a 12-year calendar hiatus between shows 130 and 131 (the show
    index is continuous across it). Shows 101-130 have no tour."""
    plan = muse_plan(pool)
    band = "Muse"
    shows = []
    for i in range(1, MUSE_TOTAL_SHOWS + 1):
        songs = tuple(name for name, indices in plan.values() if i in indices)
        d = date(2005, 1, 1) + timedelta(days=7 * (i - 1)) if i <= 130 \
            else date(2020, 1, 1) + timedelta(days=7 * (i - 131))
        tour = "Tour A" if i <= 100 else (None if i <= 130 else "Tour B")
        shows.append(SyntheticShow(f"mu-{i:03d}", band, d, tour, songs, **_extras(band, i)))
    return shows


# --- Arctic Monkeys: which songs are eligible for survival ------------------

def arctic_eligibility_history(pool: SongPool) -> list[SyntheticShow]:
    """40 shows. Song a[1]: 3 performances (eligible); a[2]: 2 (not);
    a[3]: 3 performances but one is in an undated show, so 2 dated (not);
    a[4]: 3 performances, two of them in ONE show (eligible; 2 distinct shows);
    recording-only with a year: 3 (eligible, "non-album"), 2 (not);
    recording-only without a year: 5 (not eligible)."""
    _need(pool, 10)
    if len(pool.recording_with_year) < 2 or not pool.recording_no_year:
        raise ValueError("Arctic Monkeys plan needs recording-only songs")
    a, rw, rn = pool.album, pool.recording_with_year, pool.recording_no_year
    band = "Arctic Monkeys"
    plays: dict[int, list[str]] = {i: [a[0]] for i in range(1, 41)}
    for i in (1, 2, 3):
        plays[i].append(a[1])
    for i in (4, 5):
        plays[i].append(a[2])
    for i in (6, 7):
        plays[i].append(a[3])
    plays[9] += [a[4], a[4]]
    plays[10].append(a[4])
    for i in (11, 12, 13):
        plays[i].append(rw[0])
    for i in (14, 15):
        plays[i].append(rw[1])
    for i in (16, 17, 18, 19, 20):
        plays[i].append(rn[0])
    shows = [
        SyntheticShow(f"am-{i:03d}", band, date(2010, 1, 1) + timedelta(days=4 * (i - 1)), "AM Tour",
                      tuple(plays[i]), **_extras(band, i))
        for i in range(1, 41)
    ]
    shows.append(SyntheticShow("am-u01", band, None, "AM Tour", (a[3],)))  # the undated 3rd play of a[3]
    return shows


# --- Linkin Park: a seeded pseudo-random history ----------------------------

def linkin_random_history(pool: SongPool, seed: int = 7) -> list[SyntheticShow]:
    """150 shows over three tours and a stretch without a tour, 40 songs with
    different popularity, checked against the oracle rather than by hand."""
    _need(pool, 40)
    rng = random.Random(seed)
    a = pool.album[:40]
    band = "Linkin Park"
    prob = [0.04 + 0.9 * (j / 39) ** 2 for j in range(40)]
    shows = []
    current = date(2003, 1, 1)
    for i in range(1, 151):
        current += timedelta(days=1 + int(rng.random() * 5))
        if i in (51, 101, 121):
            current += timedelta(days=200)  # a break between tours
        songs = [a[j] for j in range(40) if rng.random() < prob[j]]
        if not songs:
            songs = [a[0]]
        if i <= 50:
            tour = "LP Tour 1"
        elif i <= 100:
            tour = "LP Tour 2"
        elif i <= 120:
            tour = None
        else:
            tour = "LP Tour 3"
        shows.append(SyntheticShow(f"lp-{i:03d}", band, current, tour, tuple(songs), **_extras(band, i)))
    return shows


def all_histories(pools: dict[str, SongPool]) -> list[SyntheticShow]:
    """Every scenario, one band each (so their results stay separable)."""
    return (
        oasis_rotation_history(pools["Oasis"])
        + metallica_m72_history(pools["Metallica"])
        + muse_survival_history(pools["Muse"])
        + arctic_eligibility_history(pools["Arctic Monkeys"])
        + linkin_random_history(pools["Linkin Park"])
    )
