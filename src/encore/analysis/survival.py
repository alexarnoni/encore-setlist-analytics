"""Song survival core: show index, appearances, duration/event/censoring per
song and time window (spec-03 R6, Part B).

Pure Python — no database access here. Fetching the per-show song sets and
the catalog facts is a separate I/O layer (T8); fitting Kaplan-Meier curves
with lifelines is a separate step (T7). Keeping this module free of both
means it can be tested with plain, hand-built data (requirement 12) and
reused unchanged by both.

Conventions (approved decisions, spec-03-progress.md section 4a):

* Time is measured in band shows, not calendar time: the show index is the
  1-based position of a show in the band's full DATED history (every tour,
  "Unknown tour" included — a hiatus is invisible once shows are indexed,
  however long the calendar gap between two consecutive indices is).
* Same-date shows are ordered by show_key (Q8); undated shows have no index
  and cannot enter a duration.
* Duration is INCLUSIVE, in shows, from the live debut to the last
  appearance before the first abandonment (or to the end of history if
  censored): `last_index - debut_index + 1`. A song played once has
  duration 1.
* Abandonment (event) at a window N: after some appearance at index a, the
  next N shows (a+1 .. a+N) all exist in the band's history and NONE of them
  has the song. Only the FIRST such gap counts. A song whose last appearance
  is fewer than N shows before the end of the history cannot show a full
  gap, so it is censored at N instead. A song that reappears after its first
  abandonment is flagged `returned_after_abandonment` for that N.
* Eligible songs: at least 3 performances (raw play count, not distinct
  shows) AND matched to a studio album OR to a recording that has a release
  year (Q4/Q5: recording-only songs with no year are not eligible).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date

MIN_PERFORMANCES = 3
WINDOWS: tuple[int, ...] = (25, 50, 100)


@dataclass(frozen=True)
class ShowAppearance:
    """A song was played, in a dated show, of a band (spec-03 R1's grain:
    one row per show and canonical song — what int_show_song_sets holds)."""

    band: str
    song_key: str
    show_key: str
    show_date: date


@dataclass(frozen=True)
class SongCatalogInfo:
    """The catalog facts a survival decision needs for one song."""

    song_title: str
    reference_album: str | None
    release_year: int | None


@dataclass(frozen=True)
class SongSurvival:
    """One song's outcome at every requested window, for one band."""

    band: str
    song_key: str
    debut_index: int
    last_index: int
    total_shows: int
    duration_shows: Mapping[int, int]  # window N -> duration, inclusive
    event: Mapping[int, bool]  # window N -> abandoned (True) or censored (False)
    returned_after_abandonment: Mapping[int, bool]  # window N -> played again after the first abandonment


def band_show_index(appearances: Iterable[ShowAppearance], band: str) -> dict[str, int]:
    """1-based position of each distinct show of `band` in its full dated
    history, ordered by (show_date, show_key)."""
    dates: dict[str, date] = {}
    for a in appearances:
        if a.band == band:
            dates.setdefault(a.show_key, a.show_date)
    ordered = sorted(dates, key=lambda show_key: (dates[show_key], show_key))
    return {show_key: position for position, show_key in enumerate(ordered, start=1)}


def song_appearance_indices(
    appearances: Iterable[ShowAppearance], band: str, index: Mapping[str, int]
) -> dict[str, list[int]]:
    """Distinct show indices where each song of `band` was played, sorted."""
    per_song: dict[str, set[int]] = {}
    for a in appearances:
        if a.band == band:
            per_song.setdefault(a.song_key, set()).add(index[a.show_key])
    return {song: sorted(indices) for song, indices in per_song.items()}


def is_eligible(
    performances: int, catalog_info: SongCatalogInfo | None
) -> bool:
    """At least MIN_PERFORMANCES performances, and matched to a studio album
    or to a recording with a release year (decisions Q4/Q5, Q9)."""
    if performances < MIN_PERFORMANCES or catalog_info is None:
        return False
    return catalog_info.reference_album is not None or catalog_info.release_year is not None


def eligible_songs(
    performance_counts: Mapping[str, int], catalog: Mapping[str, SongCatalogInfo]
) -> set[str]:
    return {
        song
        for song, count in performance_counts.items()
        if is_eligible(count, catalog.get(song))
    }


def outcome_for_window(indices: list[int], total_shows: int, window: int) -> tuple[int, bool, bool]:
    """(duration_shows, event, returned_after_abandonment) for one song at
    one window N. `indices` must be sorted, non-empty show indices."""
    debut = indices[0]
    seen = set(indices)
    for appearance in indices:
        gap_is_inside_history = appearance + window <= total_shows
        gap_has_no_appearance = not any((appearance + k) in seen for k in range(1, window + 1))
        if gap_is_inside_history and gap_has_no_appearance:
            duration = appearance - debut + 1
            returned = any(i > appearance for i in indices)
            return duration, True, returned
    return total_shows - debut + 1, False, False


def compute_survival(
    appearances: Iterable[ShowAppearance],
    band: str,
    performance_counts: Mapping[str, int],
    catalog: Mapping[str, SongCatalogInfo],
    windows: tuple[int, ...] = WINDOWS,
) -> list[SongSurvival]:
    """Survival outcome of every eligible, dated-and-played song of `band`,
    at every window in `windows`.

    `performance_counts` and `catalog` key on the same song_key as
    `appearances`. A song eligible by performance count but never played in
    a DATED show (all its performances were at undated shows) has no show
    index and is silently left out — there is nothing to compute a duration
    from.
    """
    appearances = list(appearances)
    index = band_show_index(appearances, band)
    total_shows = len(index)
    per_song = song_appearance_indices(appearances, band, index)
    eligible = eligible_songs(performance_counts, catalog) & per_song.keys()

    results = []
    for song in sorted(eligible):
        indices = per_song[song]
        durations: dict[int, int] = {}
        events: dict[int, bool] = {}
        returned: dict[int, bool] = {}
        for window in windows:
            duration, event, has_returned = outcome_for_window(indices, total_shows, window)
            durations[window] = duration
            events[window] = event
            returned[window] = has_returned
        results.append(
            SongSurvival(
                band=band,
                song_key=song,
                debut_index=indices[0],
                last_index=indices[-1],
                total_shows=total_shows,
                duration_shows=durations,
                event=events,
                returned_after_abandonment=returned,
            )
        )
    return results
