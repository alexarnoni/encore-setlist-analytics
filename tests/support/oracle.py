"""Independent oracle for spec 03, in plain Python.

Everything here is written straight from the definitions in
docs/specs/spec-03-rotation-survival.md and the decisions in
docs/specs/spec-03-progress.md (section 4a), from the synthetic histories
themselves, not from the SQL models or the survival module it is used to
check. In particular the abandonment rule is implemented literally ("absent
from the next N shows after an appearance") and not with the gap arithmetic the
module uses, so a mistake in one is unlikely to be repeated in the other.

Exact `Fraction`s are used for rotation so comparisons are not blurred by
floating point; callers round when comparing with the marts.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from fractions import Fraction
from statistics import median
from typing import Mapping

from tests.support.histories import SyntheticShow

UNKNOWN_TOUR = "Unknown tour"
MIN_TOUR_SHOWS = 5
WINDOWS = (25, 50, 100)
MIN_PERFORMANCES = 3
NON_ALBUM = "non-album"


def tour_of(show: SyntheticShow) -> str:
    return show.tour_name or UNKNOWN_TOUR


def dated_shows(shows: list[SyntheticShow]) -> list[SyntheticShow]:
    """Shows that can be ordered and have at least one matched song."""
    return [s for s in shows if s.show_date is not None and s.songs]


def order_key(show: SyntheticShow) -> tuple:
    return (show.show_date, show.setlist_id)


def show_sets(shows: list[SyntheticShow]) -> dict[str, frozenset[str]]:
    return {s.setlist_id: frozenset(s.songs) for s in dated_shows(shows)}


# --- Rotation ---------------------------------------------------------------

def jaccard(a: frozenset[str], b: frozenset[str]) -> Fraction:
    return Fraction(len(a & b), len(a | b))


@dataclass(frozen=True)
class Pair:
    band: str
    tour: str
    first_id: str
    second_id: str
    second_date: object
    jaccard: Fraction


def consecutive_pairs(shows: list[SyntheticShow]) -> list[Pair]:
    """Adjacent shows of the same band and tour, in (date, id) order;
    "Unknown tour" shows are never paired."""
    by_tour: dict[tuple[str, str], list[SyntheticShow]] = defaultdict(list)
    for s in dated_shows(shows):
        if tour_of(s) != UNKNOWN_TOUR:
            by_tour[(s.band, tour_of(s))].append(s)
    pairs = []
    for (band, tour), group in by_tour.items():
        group.sort(key=order_key)
        for first, second in zip(group, group[1:]):
            pairs.append(Pair(band, tour, first.setlist_id, second.setlist_id, second.show_date,
                              jaccard(frozenset(first.songs), frozenset(second.songs))))
    return pairs


@dataclass(frozen=True)
class TourStats:
    shows: int
    pairs: int
    mean_jaccard: Fraction
    rotation: Fraction
    median_setlist_size: Fraction
    core_songs: int
    distinct_songs: int
    first_year: int
    last_year: int


def tour_rotation(shows: list[SyntheticShow]) -> dict[tuple[str, str], TourStats]:
    """Rotation per (band, tour) for tours with at least MIN_TOUR_SHOWS shows."""
    tours: dict[tuple[str, str], list[SyntheticShow]] = defaultdict(list)
    for s in dated_shows(shows):
        if tour_of(s) != UNKNOWN_TOUR:
            tours[(s.band, tour_of(s))].append(s)
    pairs_by_tour: dict[tuple[str, str], list[Pair]] = defaultdict(list)
    for p in consecutive_pairs(shows):
        pairs_by_tour[(p.band, p.tour)].append(p)

    result = {}
    for key, group in tours.items():
        if len(group) < MIN_TOUR_SHOWS:
            continue
        pairs = pairs_by_tour[key]
        mean = sum((p.jaccard for p in pairs), Fraction(0)) / len(pairs)
        appearances: dict[str, int] = defaultdict(int)
        for s in group:
            for song in set(s.songs):
                appearances[song] += 1
        result[key] = TourStats(
            shows=len(group),
            pairs=len(pairs),
            mean_jaccard=mean,
            rotation=1 - mean,
            median_setlist_size=Fraction(median(len(set(s.songs)) for s in group)),
            core_songs=sum(1 for n in appearances.values() if n * 10 >= len(group) * 9),
            distinct_songs=len(appearances),
            first_year=min(s.show_date.year for s in group),
            last_year=max(s.show_date.year for s in group),
        )
    return result


@dataclass(frozen=True)
class YearStats:
    pairs: int
    mean_jaccard: Fraction
    rotation: Fraction


def band_rotation_by_year(shows: list[SyntheticShow]) -> dict[tuple[str, int], YearStats]:
    """Pairs of the included tours, in the year of the pair's SECOND show."""
    included = set(tour_rotation(shows))
    by_year: dict[tuple[str, int], list[Fraction]] = defaultdict(list)
    for p in consecutive_pairs(shows):
        if (p.band, p.tour) in included:
            by_year[(p.band, p.second_date.year)].append(p.jaccard)
    return {
        key: YearStats(len(values), sum(values, Fraction(0)) / len(values),
                       1 - sum(values, Fraction(0)) / len(values))
        for key, values in by_year.items()
    }


# --- Survival ---------------------------------------------------------------

@dataclass(frozen=True)
class CatalogInfo:
    reference_album: str | None
    release_year: int | None


@dataclass(frozen=True)
class Outcome:
    debut_index: int
    last_index: int  # the song's last appearance
    duration: int
    event: bool  # left for good: the FINAL gap is at least `window` shows
    returned: bool  # at least one intermediate gap of `window` shows or more
    gaps: int  # number of intermediate gaps of `window` shows or more


def band_show_index(shows: list[SyntheticShow], band: str) -> dict[str, int]:
    """1-based position of each dated show in the band's full history
    (every tour, "Unknown tour" included)."""
    ordered = sorted((s for s in dated_shows(shows) if s.band == band), key=order_key)
    return {s.setlist_id: i for i, s in enumerate(ordered, start=1)}


def appearances(shows: list[SyntheticShow], band: str) -> tuple[dict[str, list[int]], int]:
    """Distinct show indices per song, and the total number of shows."""
    index = band_show_index(shows, band)
    per_song: dict[str, set[int]] = defaultdict(set)
    for s in dated_shows(shows):
        if s.band == band:
            for song in s.songs:
                per_song[song].add(index[s.setlist_id])
    return {song: sorted(idx) for song, idx in per_song.items()}, len(index)


def performances(shows: list[SyntheticShow], band: str) -> dict[str, int]:
    """Matched performances per song in shows with a known date."""
    count: dict[str, int] = defaultdict(int)
    for s in dated_shows(shows):
        if s.band == band:
            for song in s.songs:
                count[song] += 1
    return dict(count)


def outcome(indices: list[int], total: int, window: int) -> Outcome:
    """By the literal definition. After an appearance at index a, the song has
    a GAP when shows a+1..a+window all exist and none of them has the song. A
    gap followed by a later appearance is intermediate (the song returned); a
    gap with no later appearance is the final one, i.e. the song left for good
    and is an event. Duration is inclusive (last - debut + 1); a censored song
    that never had a gap runs to the end of the history instead."""
    seen = set(indices)
    debut, last = indices[0], indices[-1]
    gaps = 0
    left_for_good = False
    for a in indices:
        if a + window <= total and not any((a + k) in seen for k in range(1, window + 1)):
            if any(i > a for i in indices):
                gaps += 1
            else:
                left_for_good = True
    if left_for_good or gaps:
        return Outcome(debut, last, last - debut + 1, left_for_good, gaps > 0, gaps)
    return Outcome(debut, last, total - debut + 1, False, False, 0)


def eligible_songs(shows: list[SyntheticShow], band: str,
                   catalog: Mapping[str, CatalogInfo]) -> list[str]:
    """At least 3 performances, and matched to a studio album or to a
    recording that has a release year."""
    perf = performances(shows, band)
    return sorted(
        song for song, n in perf.items()
        if n >= MIN_PERFORMANCES
        and (catalog[song].reference_album is not None or catalog[song].release_year is not None)
    )


def survival_outcomes(shows: list[SyntheticShow], band: str, catalog: Mapping[str, CatalogInfo],
                      window: int) -> dict[str, Outcome]:
    apps, total = appearances(shows, band)
    return {song: outcome(apps[song], total, window) for song in eligible_songs(shows, band, catalog)}
