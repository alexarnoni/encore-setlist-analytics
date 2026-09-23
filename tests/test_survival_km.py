"""Kaplan-Meier fitting (spec-03 T7): fit_curve and group_by_album, compared
against a hand-written product-limit estimator (requirement: not lifelines'
own algorithm re-run, an independent one) and against basic sanity
properties (bounds, monotonicity, events + censored = songs).
"""

import pytest

from encore.analysis.survival import (
    ALL_ALBUMS,
    NON_ALBUM,
    SongSurvival,
    fit_curve,
    group_by_album,
)


def _outcome(band, song, album, duration, event, window=50):
    """A minimal SongSurvival with only the fields fit_curve() reads."""
    return SongSurvival(
        band=band, song_key=song, album_label=album,
        debut_index=1, last_index=duration, total_shows=1000,
        duration_shows={window: duration}, event={window: event},
        returned_after_abandonment={window: False}, gaps_count={window: 0},
    )


def hand_written_km(durations: list[int], events: list[bool]) -> dict[int, float]:
    """An independent product-limit estimator (Kaplan & Meier 1958), not
    copied from lifelines: at each distinct time an EVENT happens,
    S(t) = S(t-) * (1 - d/n), where n is everyone still at risk (duration >=
    t, event or censored) and d is how many of those events happened exactly
    at t. Censoring alone never multiplies S; it only shrinks the risk set
    for later times. Returns {time: S(t)} for every distinct duration."""
    times = sorted(set(durations))
    survival = {}
    s = 1.0
    for t in times:
        at_risk = sum(1 for d in durations if d >= t)
        events_at_t = sum(1 for d, e in zip(durations, events) if d == t and e)
        if events_at_t:
            s *= 1 - events_at_t / at_risk
        survival[t] = s
    return survival


# A small dataset with ties on both events and censoring, no clean pattern.
DURATIONS = [1, 1, 3, 3, 5, 5, 5, 10, 10, 20]
EVENTS = [True, False, True, True, False, False, True, True, False, False]


def test_fit_curve_matches_an_independent_product_limit_estimator():
    outcomes = [_outcome("B", f"s{i}", "A", d, e) for i, (d, e) in enumerate(zip(DURATIONS, EVENTS))]

    points, summary = fit_curve(outcomes, window=50)

    expected = hand_written_km(DURATIONS, EVENTS)
    got = {p.t_shows: p.survival_probability for p in points if p.t_shows > 0}
    assert got.keys() == expected.keys()
    for t, expected_s in expected.items():
        assert got[t] == pytest.approx(expected_s, abs=1e-9), t

    assert summary.songs == 10
    assert summary.events == sum(EVENTS)
    assert summary.censored == 10 - sum(EVENTS)


def test_curve_starts_at_t_zero_with_probability_one_and_everyone_at_risk():
    outcomes = [_outcome("B", f"s{i}", "A", d, e) for i, (d, e) in enumerate(zip(DURATIONS, EVENTS))]

    points, _ = fit_curve(outcomes, window=50)

    first = points[0]
    assert (first.t_shows, first.survival_probability, first.at_risk, first.events) == (0, 1.0, len(outcomes), 0)


def test_curve_is_non_increasing_and_bounded():
    outcomes = [_outcome("B", f"s{i}", "A", d, e) for i, (d, e) in enumerate(zip(DURATIONS, EVENTS))]

    points, _ = fit_curve(outcomes, window=50)

    previous = 1.0
    for point in points:
        assert 0 <= point.survival_probability <= 1
        assert point.ci_lower <= point.survival_probability <= point.ci_upper
        assert 0 <= point.ci_lower and point.ci_upper <= 1
        assert point.survival_probability <= previous + 1e-9
        previous = point.survival_probability


def test_events_plus_censored_equals_songs():
    outcomes = [_outcome("B", f"s{i}", "A", d, e) for i, (d, e) in enumerate(zip(DURATIONS, EVENTS))]

    _, summary = fit_curve(outcomes, window=50)

    assert summary.events + summary.censored == summary.songs


def test_median_is_none_when_the_curve_never_drops_below_half():
    outcomes = [_outcome("B", f"s{i}", "A", 10, False) for i in range(5)]  # all censored: never drops

    _, summary = fit_curve(outcomes, window=50)

    assert summary.median_survival_shows is None


def test_median_is_set_when_the_curve_does_drop_below_half():
    # 4 songs, 3 abandoned at the same time: survival drops from 1.0 to 0.25.
    outcomes = [_outcome("B", f"s{i}", "A", 10, True) for i in range(3)] + [_outcome("B", "s3", "A", 10, False)]

    _, summary = fit_curve(outcomes, window=50)

    assert summary.median_survival_shows == 10


def test_fit_curve_of_an_empty_group_is_a_flat_none():
    points, summary = fit_curve([], window=50)

    assert points == []
    assert summary.songs == 0
    assert summary.events == 0 and summary.censored == 0 and summary.median_survival_shows is None


def test_group_by_album_has_all_plus_one_group_per_album_including_non_album():
    outcomes = [
        _outcome("B", "s1", "Album X", 5, True),
        _outcome("B", "s2", "Album X", 8, False),
        _outcome("B", "s3", "Album Y", 3, True),
        _outcome("B", "s4", NON_ALBUM, 20, False),
    ]

    groups = group_by_album(outcomes)

    assert set(groups) == {ALL_ALBUMS, "Album X", "Album Y", NON_ALBUM}
    assert groups[ALL_ALBUMS] == outcomes
    assert {o.song_key for o in groups["Album X"]} == {"s1", "s2"}
    assert {o.song_key for o in groups["Album Y"]} == {"s3"}
    assert {o.song_key for o in groups[NON_ALBUM]} == {"s4"}


def test_group_by_album_of_no_songs_still_has_an_empty_all_group():
    assert group_by_album([]) == {ALL_ALBUMS: []}


def test_hand_written_estimator_agrees_with_a_textbook_no_censoring_case():
    """Sanity check on the test helper itself: with no censoring at all, the
    product-limit estimator is just 1 - (rank / n) at each distinct death
    time — the plain empirical survival function."""
    durations = [1, 2, 3, 4, 5]
    events = [True] * 5

    survival = hand_written_km(durations, events)

    assert survival == pytest.approx({1: 0.8, 2: 0.6, 3: 0.4, 4: 0.2, 5: 0.0})
