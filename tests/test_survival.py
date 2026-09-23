"""Unit tests for the survival core, with hand-built show histories
(spec-03 requirement 12): a song abandoned exactly at the window, one show
short of it (not abandoned), a censored song, a song that returns after
abandonment, and a band with a long calendar hiatus that must not look like
an abandonment (time is band shows, not calendar time).
"""

from datetime import date, timedelta

import pytest

from encore.analysis.survival import (
    MIN_PERFORMANCES,
    ShowAppearance,
    SongCatalogInfo,
    band_show_index,
    compute_survival,
    eligible_songs,
    is_eligible,
    outcome_for_window,
    song_appearance_indices,
)

BAND = "TestBand"
ALBUM_SONG = SongCatalogInfo("Album Song", "Some Album", 2000)
RECORDING_WITH_YEAR = SongCatalogInfo("Recording Song", None, 2001)
RECORDING_NO_YEAR = SongCatalogInfo("Undated Recording", None, None)


def _shows(n: int, start: date = date(2000, 1, 1)) -> list[date]:
    """n consecutive weekly show dates."""
    return [start + timedelta(days=7 * i) for i in range(n)]


def _appearance(band: str, song: str, show_index: int, dates: list[date]) -> ShowAppearance:
    return ShowAppearance(band, song, f"s{show_index}", dates[show_index - 1])


def _all_shows_appearances(band: str, dates: list[date]) -> list[ShowAppearance]:
    """A filler song played at every show, so every date becomes a real show
    in the band's history even where the song under test is silent."""
    return [_appearance(band, "Filler", i, dates) for i in range(1, len(dates) + 1)]


# --- show index and appearance indices --------------------------------------


def test_show_index_orders_by_date_then_show_key():
    dates = _shows(3)
    appearances = [
        ShowAppearance(BAND, "X", "b", dates[1]),
        ShowAppearance(BAND, "X", "a", dates[1]),  # same date as "b", key decides
        ShowAppearance(BAND, "X", "c", dates[2]),
        ShowAppearance(BAND, "X", "z", dates[0]),
    ]

    index = band_show_index(appearances, BAND)

    assert index == {"z": 1, "a": 2, "b": 3, "c": 4}


def test_show_index_ignores_other_bands():
    dates = _shows(2)
    appearances = [ShowAppearance(BAND, "X", "s1", dates[0]), ShowAppearance("Other", "X", "s2", dates[1])]

    assert band_show_index(appearances, BAND) == {"s1": 1}


def test_song_appearance_indices_deduplicates_repeats_within_a_show():
    dates = _shows(1)
    appearances = [ShowAppearance(BAND, "X", "s1", dates[0])] * 3  # played 3 times in one show
    index = band_show_index(appearances, BAND)

    assert song_appearance_indices(appearances, BAND, index) == {"X": [1]}


# --- eligibility -------------------------------------------------------------


def test_eligibility_needs_minimum_performances_and_a_dateable_source():
    assert is_eligible(MIN_PERFORMANCES, ALBUM_SONG)
    assert is_eligible(MIN_PERFORMANCES, RECORDING_WITH_YEAR)
    assert not is_eligible(MIN_PERFORMANCES - 1, ALBUM_SONG)  # too few performances
    assert not is_eligible(MIN_PERFORMANCES, RECORDING_NO_YEAR)  # recording, no year: not eligible
    assert not is_eligible(MIN_PERFORMANCES, None)  # not even in the catalog


def test_eligible_songs_filters_a_mapping():
    counts = {"a": 3, "b": 2, "c": 10}
    catalog = {"a": ALBUM_SONG, "b": ALBUM_SONG, "c": RECORDING_NO_YEAR}

    assert eligible_songs(counts, catalog) == {"a"}


# --- outcome_for_window: the abandonment rule -------------------------------
#
# Abandonment is the FINAL gap only: the last appearance is at least N shows
# before the end of the history. A song that had an intermediate gap and came
# back is censored, with duration debut -> last appearance.


def test_song_that_left_for_good_is_an_event():
    # played at 1, silent for the 50 shows after it, history has 100 shows.
    out = outcome_for_window([1], total_shows=100, window=50)

    assert out == (1, True, False, 0)


def test_final_gap_of_exactly_the_window_is_an_abandonment():
    # appearance at 1, window 50, and the history has EXACTLY 51 shows: the
    # silent tail (shows 2..51) is a full in-history gap (last + window == total).
    assert outcome_for_window([1], total_shows=51, window=50) == (1, True, False, 0)
    # one show short of that boundary: the gap needs one more show than exists.
    assert outcome_for_window([1], total_shows=50, window=50) == (50, False, False, 0)


def test_song_still_being_played_is_censored_to_the_end_of_history():
    out = outcome_for_window([1, 5, 9], total_shows=10, window=50)

    assert out == (10 - 1 + 1, False, False, 0)
    assert outcome_for_window([70], total_shows=100, window=50) == (31, False, False, 0)  # 30 shows remain: censored


def test_song_that_returns_and_is_still_played_is_censored_not_abandoned():
    # gap of 6 shows (2..7 silent) after index 1, then it comes back and is
    # played until the end: it returned, so it is NOT an abandonment.
    out = outcome_for_window([1, 8, 9, 10], total_shows=11, window=5)

    assert out.event is False
    assert out.returned_after_abandonment is True
    assert out.gaps_count == 1
    assert out.duration_shows == 10 - 1 + 1  # debut to its last appearance, not to the end of history


def test_song_that_returns_and_then_leaves_for_good_is_an_event_with_the_last_appearance():
    # intermediate gap after 3 (5 silent shows), back at 9, then silent for the
    # last 11 shows: left for good, after having returned once.
    out = outcome_for_window([1, 2, 3, 9], total_shows=20, window=5)

    assert out == (9 - 1 + 1, True, True, 1)


def test_gap_one_show_short_of_the_window_is_not_an_intermediate_gap():
    # appearances at 1 and 51: only 49 silent shows between them.
    out = outcome_for_window([1, 51], total_shows=60, window=50)

    assert out.gaps_count == 0
    assert out.returned_after_abandonment is False
    assert out.event is False
    assert out.duration_shows == 60 - 1 + 1  # never had a gap: runs to the end of history


def test_intermediate_gap_of_exactly_the_window_counts():
    out = outcome_for_window([1, 52], total_shows=60, window=50)  # shows 2..51 silent: 50 of them

    assert out.gaps_count == 1
    assert out.returned_after_abandonment is True
    assert out.event is False
    assert out.duration_shows == 52 - 1 + 1


def test_gaps_count_counts_every_intermediate_gap_and_ignores_short_ones():
    # gaps of 5, 2, 6 silent shows between appearances; window 5 -> two count.
    indices = [1, 7, 10, 17]
    out = outcome_for_window(indices, total_shows=18, window=5)

    assert out.gaps_count == 2
    assert out.event is False  # 1 show after the last appearance: still in the repertoire
    assert out.duration_shows == 17 - 1 + 1


def test_a_song_played_once_has_duration_one():
    assert outcome_for_window([7], total_shows=100, window=50) == (1, True, False, 0)  # 93 silent shows follow: abandoned


def test_the_first_gap_no_longer_decides_the_event():
    # the old rule called this an event at the first 5-show gap (after index 3);
    # the song is back and played to the end, so now it is censored.
    out = outcome_for_window([1, 2, 3, 9, 10, 11, 12], total_shows=12, window=5)

    assert (out.event, out.gaps_count) == (False, 1)


# --- compute_survival: end-to-end on hand-built band histories ---------------


def test_full_scenario_abandoned_censored_returning_and_hiatus():
    """One band, one history, four songs with known outcomes at N=5:
    - "Exact": abandoned with a gap of exactly 5.
    - "Short": played close to the end of history, tail gap under the window (censored).
    - "Returns": leaves, comes back, then leaves for good (an event, last appearance 10).
    - "Stays": leaves, comes back and is still played near the end (censored, returned).
    - "Hiatus": played continuously across the show-index boundary that
      falls on a 20-calendar-year gap (shows 10 to 11) and on to the end of
      history — must NOT be flagged abandoned, because the show index has no
      silent gap there at all; only calendar time does.
    """
    dates = _shows(10, start=date(2000, 1, 1)) + _shows(10, start=date(2020, 1, 1))  # a 20-year hiatus mid-history
    appearances = _all_shows_appearances(BAND, dates)
    appearances += [
        _appearance(BAND, "Exact", 1, dates), _appearance(BAND, "Exact", 2, dates),
        _appearance(BAND, "Exact", 3, dates),
        _appearance(BAND, "Short", 16, dates), _appearance(BAND, "Short", 17, dates),
        _appearance(BAND, "Short", 18, dates), _appearance(BAND, "Short", 19, dates),
        _appearance(BAND, "Returns", 1, dates), _appearance(BAND, "Returns", 2, dates),
        _appearance(BAND, "Returns", 3, dates), _appearance(BAND, "Returns", 9, dates),
        _appearance(BAND, "Returns", 10, dates),
        *[_appearance(BAND, "Stays", i, dates) for i in (1, 2, 3, *range(10, 19))],
        *[_appearance(BAND, "Hiatus", i, dates) for i in range(9, 21)],  # straight through the hiatus boundary
    ]
    counts = {"Filler": 20, "Exact": 4, "Short": 4, "Returns": 5, "Stays": 12, "Hiatus": 12}
    catalog = {name: ALBUM_SONG for name in counts}

    outcomes = {o.song_key: o for o in compute_survival(appearances, BAND, counts, catalog, windows=(5,))}

    assert outcomes["Exact"].event[5] is True
    assert outcomes["Exact"].duration_shows[5] == 3  # debut 1, last appearance 3: 3-1+1
    assert outcomes["Exact"].returned_after_abandonment[5] is False
    assert outcomes["Exact"].gaps_count[5] == 0

    assert outcomes["Short"].event[5] is False  # last appearance at 19, only 1 show remains: no full gap ever
    assert outcomes["Short"].duration_shows[5] == 20 - 16 + 1  # censored: debut 16 to the end of history

    # "Returns" left after show 3, came back at 9 and 10, and the history ends
    # at 20 (10 silent shows after 10): it returned and then left for good.
    assert outcomes["Returns"].event[5] is True
    assert outcomes["Returns"].duration_shows[5] == 10 - 1 + 1
    assert outcomes["Returns"].returned_after_abandonment[5] is True
    assert outcomes["Returns"].gaps_count[5] == 1

    # "Stays" has one 6-show gap (shows 4..9) and is back until show 18, two
    # shows before the end: it returned, so it is censored, and its duration
    # stops at its last appearance.
    assert outcomes["Stays"].event[5] is False
    assert outcomes["Stays"].duration_shows[5] == 18 - 1 + 1
    assert outcomes["Stays"].returned_after_abandonment[5] is True
    assert outcomes["Stays"].gaps_count[5] == 1

    # Hiatus is played at every show from index 9 to 20 — a continuous run
    # of show indices, even though the calendar gap between shows 10 and 11
    # is ~20 years. No silent show-index gap ever appears, so no abandonment.
    assert outcomes["Hiatus"].event[5] is False
    assert outcomes["Hiatus"].duration_shows[5] == 20 - 9 + 1
    assert outcomes["Hiatus"].gaps_count[5] == 0
    assert "Filler" in {o.song_key for o in compute_survival(appearances, BAND, counts, catalog, windows=(5,))}


def test_multiple_windows_can_disagree_for_the_same_song():
    dates = _shows(30)
    appearances = _all_shows_appearances(BAND, dates)
    appearances += [_appearance(BAND, "X", 1, dates), _appearance(BAND, "X", 2, dates),
                    _appearance(BAND, "X", 3, dates)]
    counts = {"Filler": 30, "X": 3}
    catalog = {"Filler": ALBUM_SONG, "X": ALBUM_SONG}

    (outcome,) = [o for o in compute_survival(appearances, BAND, counts, catalog, windows=(5, 50)) if o.song_key == "X"]

    assert outcome.event[5] is True  # 27 silent shows after index 3: abandoned at N=5
    assert outcome.event[50] is False  # not enough shows remain for a 50-show gap: censored
    assert outcome.duration_shows[50] == 30 - 1 + 1


def test_ineligible_songs_are_left_out_even_if_they_have_appearances():
    dates = _shows(5)
    appearances = _all_shows_appearances(BAND, dates)
    appearances.append(_appearance(BAND, "TooFew", 1, dates))
    counts = {"Filler": 5, "TooFew": 2}
    catalog = {"Filler": ALBUM_SONG, "TooFew": ALBUM_SONG}

    songs = {o.song_key for o in compute_survival(appearances, BAND, counts, catalog)}

    assert songs == {"Filler"}


def test_a_song_played_only_in_undated_shows_has_no_appearances_and_is_skipped():
    dates = _shows(5)
    appearances = _all_shows_appearances(BAND, dates)  # "Ghost" never appears here at all
    counts = {"Filler": 5, "Ghost": 10}  # high performance count, but no dated appearance rows
    catalog = {"Filler": ALBUM_SONG, "Ghost": ALBUM_SONG}

    songs = {o.song_key for o in compute_survival(appearances, BAND, counts, catalog)}

    assert songs == {"Filler"}


def test_compute_survival_ignores_other_bands_entirely():
    dates = _shows(5)
    appearances = _all_shows_appearances(BAND, dates) + _all_shows_appearances("Other", dates)
    counts = {"Filler": 5}
    catalog = {"Filler": ALBUM_SONG}

    outcomes = compute_survival(appearances, BAND, counts, catalog)

    assert all(o.band == BAND for o in outcomes)
    assert compute_survival(appearances, BAND, counts, catalog)[0].total_shows == 5
