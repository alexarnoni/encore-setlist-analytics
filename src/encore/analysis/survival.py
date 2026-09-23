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

from lifelines import KaplanMeierFitter

MIN_PERFORMANCES = 3
WINDOWS: tuple[int, ...] = (25, 50, 100)

# Kaplan-Meier grouping labels (requirement 6: "per band, and per band and
# reference album"). ALL_ALBUMS is every eligible song of the band regardless
# of album; NON_ALBUM is the label for eligible recording-only songs (no
# reference album, matched through a dated recording — Q4/Q5).
ALL_ALBUMS = "all"
NON_ALBUM = "non-album"


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
    album_label: str  # the song's reference_album, or NON_ALBUM
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
                album_label=catalog[song].reference_album or NON_ALBUM,
                debut_index=indices[0],
                last_index=indices[-1],
                total_shows=total_shows,
                duration_shows=durations,
                event=events,
                returned_after_abandonment=returned,
            )
        )
    return results


# --- Kaplan-Meier curves (spec-03 T7) ---------------------------------------


@dataclass(frozen=True)
class CurvePoint:
    """One row of a survival curve at one time step."""

    t_shows: int
    at_risk: int
    events: int
    survival_probability: float
    ci_lower: float
    ci_upper: float


@dataclass(frozen=True)
class CurveSummary:
    """One (band, album, window) group's headline numbers."""

    songs: int
    events: int
    censored: int
    median_survival_shows: float | None  # None when the curve never drops below 0.5


def group_by_album(outcomes: Iterable[SongSurvival]) -> dict[str, list[SongSurvival]]:
    """One band's outcomes, grouped for Kaplan-Meier fitting: `ALL_ALBUMS`
    (every eligible song) plus one group per album label (`NON_ALBUM`
    included). A studio album that happened to be named "all" would collide
    with the `ALL_ALBUMS` key — not handled; no real album is named that."""
    outcomes = list(outcomes)
    groups: dict[str, list[SongSurvival]] = {ALL_ALBUMS: outcomes}
    for outcome in outcomes:
        groups.setdefault(outcome.album_label, []).append(outcome)
    return groups


def fit_curve(outcomes: list[SongSurvival], window: int) -> tuple[list[CurvePoint], CurveSummary]:
    """Fit one Kaplan-Meier curve from `outcomes` (already the (band, album)
    group wanted) at window N.

    The time grid (decision Q7) is exactly the KM timeline lifelines produces
    — the distinct event and censoring times, which always starts at t=0 with
    probability 1 and every song still at risk — so no extra grid handling is
    needed here.
    """
    if not outcomes:
        return [], CurveSummary(songs=0, events=0, censored=0, median_survival_shows=None)

    durations = [o.duration_shows[window] for o in outcomes]
    event_flags = [o.event[window] for o in outcomes]

    fitter = KaplanMeierFitter()
    fitter.fit(durations, event_observed=event_flags)

    survival = fitter.survival_function_.iloc[:, 0]
    confidence = fitter.confidence_interval_
    at_risk = fitter.event_table["at_risk"]
    observed = fitter.event_table["observed"]

    points = [
        CurvePoint(
            t_shows=int(t),
            at_risk=int(at_risk.loc[t]),
            events=int(observed.loc[t]),
            survival_probability=float(survival.loc[t]),
            ci_lower=float(confidence.iloc[:, 0].loc[t]),
            ci_upper=float(confidence.iloc[:, 1].loc[t]),
        )
        for t in survival.index
    ]

    total_events = sum(event_flags)
    songs = len(outcomes)
    median = fitter.median_survival_time_
    median_shows = None if median != median or median == float("inf") else float(median)  # median != median: NaN
    summary = CurveSummary(songs=songs, events=total_events, censored=songs - total_events,
                            median_survival_shows=median_shows)
    return points, summary
