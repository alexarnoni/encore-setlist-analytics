"""A small deterministic fake of the `analytics` marts, column-for-column like the real ones.

Seven bands, years 2000-2004, two tours, two albums plus `non-album` and the
band total `all`, and all three survival windows. Values are simple formulas of
the band index and year so tests can compute expected results by hand.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

BANDS = [
    "Arctic Monkeys", "Oasis", "Linkin Park", "Twenty One Pilots",
    "Muse", "Metallica", "Avenged Sevenfold",
]
YEARS = [2000, 2001, 2002, 2003, 2004]
TOURS = {"Tour A": [2000, 2001, 2002], "Tour B": [2003, 2004]}
ALBUMS = ["Album One", "Album Two", "non-album", "all"]
WINDOWS = [25, 50, 100]
COMPUTED_AT = datetime(2026, 9, 23, 6, 30, tzinfo=timezone.utc)
# Years outside 2000-2004 that exist only to feed placeholders: touring intensity "from 2015 on"
# (rotation) and Muse's two weakly matched early years (match quality).
LATE_ROTATION_YEARS = [2015, 2016]
MUSE_WEAK_YEARS = {1994: (9, 0), 1995: (50, 12)}  # year -> (performances, matched)


def fake_marts() -> dict[str, pd.DataFrame]:
    """Return the six marts the site reads, keyed by table name."""
    age, rot_year, tour, quality, curves, summary = [], [], [], [], [], []
    for b, band in enumerate(BANDS):
        for tour_name, years in TOURS.items():
            for y in years:
                age.append(dict(
                    band=band, tour_name=tour_name, show_year=y, shows=10 + b, performances=200 + b,
                    matched_performances=190 + b, aged_performances=180 + b, match_rate=0.95,
                    avg_repertoire_age=5.0 + b + (y - 2000), median_repertoire_age=4.0 + b + (y - 2000),
                    oldest_song_year=1990, newest_song_year=y, computed_at=COMPUTED_AT))
            tour.append(dict(
                band=band, tour_name=tour_name, first_year=years[0], last_year=years[-1],
                shows=10 * len(years), pairs=10 * len(years) - 1, mean_jaccard=0.6, rotation=0.4,
                median_setlist_size=20, core_songs=8, distinct_songs=40, computed_at=COMPUTED_AT))
        for y in YEARS:
            rot_year.append(dict(band=band, show_year=y, pairs=20 + b, mean_jaccard=0.7 - 0.01 * b,
                                 rotation=0.3 + 0.01 * b, computed_at=COMPUTED_AT))
            quality.append(dict(
                band=band, show_year=y, performances=400, matched_performances=380,
                match_rate_by_performance=0.95, distinct_songs=60, distinct_songs_matched=55,
                match_rate_by_title=0.9, match_rate_by_album=0.85, computed_at=COMPUTED_AT))
        for y in LATE_ROTATION_YEARS:
            rot_year.append(dict(band=band, show_year=y, pairs=30 + b, mean_jaccard=0.6, rotation=0.4,
                                 computed_at=COMPUTED_AT))
        if band == "Muse":
            for y, (perf, matched) in MUSE_WEAK_YEARS.items():
                quality.append(dict(
                    band=band, show_year=y, performances=perf, matched_performances=matched,
                    match_rate_by_performance=matched / perf, distinct_songs=5, distinct_songs_matched=1,
                    match_rate_by_title=0.2, match_rate_by_album=0.1, computed_at=COMPUTED_AT))
        for n in WINDOWS:
            for album in ALBUMS:
                songs = 30 if album == "all" else 10
                events = songs // 2
                summary.append(dict(
                    band=band, album=album, n_window=n, songs=songs, events=events,
                    censored=songs - events, median_survival_shows=None if album == "non-album" else 100.0 + n + b,
                    computed_at=COMPUTED_AT))
                for t in range(1, 6):
                    curves.append(dict(
                        band=band, album=album, n_window=n, t_shows=t * 10, at_risk=songs - t,
                        events=1, survival_probability=1.0 - 0.15 * t, ci_lower=0.9 - 0.15 * t,
                        ci_upper=1.0, computed_at=COMPUTED_AT))
    frames = {
        "mart_repertoire_age": age, "mart_band_rotation_by_year": rot_year, "mart_tour_rotation": tour,
        "mart_match_quality": quality, "mart_survival_curves": curves, "mart_survival_summary": summary,
    }
    return {name: pd.DataFrame(rows) for name, rows in frames.items()}
