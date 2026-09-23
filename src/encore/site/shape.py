"""Pure aggregations from the marts to what the pages show.

Every function takes DataFrames shaped like the `analytics` marts and returns a
DataFrame or plain values; nothing here touches the database or the filesystem.
Conventions (docs/methodology.md): survival is measured in shows, the main
window is N = 50, years with fewer than 5 show pairs are drawn as thin data,
and albums with fewer than 5 songs are listed but flagged, not drawn.
"""

from __future__ import annotations

import pandas as pd

MAIN_WINDOW = 50
WINDOWS = (25, 50, 100)
MIN_PAIRS = 5
MIN_SONGS = 5
MIN_TOUR_CELL_SHOWS = 15
UNKNOWN_TOUR = "Unknown tour"
BAND_TOTAL = "all"
NON_ALBUM = "non-album"
# Cross-band survival comparisons use one horizon (shows since live debut) that every band's curve reaches.
COMMON_HORIZON = 500


def age_by_year(age: pd.DataFrame, band: str) -> pd.DataFrame:
    """Repertoire age per year: the performance-weighted mean over the year's tour cells.

    Weights are `aged_performances`, the performances that entered each cell's
    average, so the result equals the mean over all of the year's aged performances.
    Columns: show_year, avg_age, aged_performances.
    """
    rows = age[(age["band"] == band) & (age["aged_performances"] > 0) & age["avg_repertoire_age"].notna()].copy()
    rows["weighted"] = rows["avg_repertoire_age"] * rows["aged_performances"]
    grouped = rows.groupby("show_year", as_index=False).agg(
        weighted=("weighted", "sum"), aged_performances=("aged_performances", "sum"))
    grouped["avg_age"] = grouped["weighted"] / grouped["aged_performances"]
    return grouped[["show_year", "avg_age", "aged_performances"]].sort_values("show_year").reset_index(drop=True)


def age_by_tour_cell(age: pd.DataFrame, band: str, min_shows: int = MIN_TOUR_CELL_SHOWS) -> pd.DataFrame:
    """Median repertoire age of each tour-and-year cell, where the median genuinely exists.

    A tour's median over several years cannot be rebuilt from the per-year
    medians, so a tour that spans years appears once per year. "Unknown tour"
    is not a tour and cells with fewer than `min_shows` shows are too thin.
    Columns: tour_name, show_year, shows, median_age, avg_age; oldest first.
    """
    rows = age[
        (age["band"] == band) & (age["tour_name"] != UNKNOWN_TOUR) & (age["shows"] >= min_shows)
        & age["median_repertoire_age"].notna()
    ]
    out = rows.rename(columns={"median_repertoire_age": "median_age", "avg_repertoire_age": "avg_age"})
    return out[["tour_name", "show_year", "shows", "median_age", "avg_age"]].sort_values(
        ["show_year", "tour_name"]).reset_index(drop=True)


def rotation_by_year(rot: pd.DataFrame, band: str) -> pd.DataFrame:
    """Rotation per year with a `thin` flag for years under MIN_PAIRS show pairs."""
    rows = rot[rot["band"] == band][["show_year", "rotation", "pairs"]].sort_values("show_year")
    rows = rows.assign(thin=rows["pairs"] < MIN_PAIRS)
    return rows.reset_index(drop=True)


def survival_albums(summary: pd.DataFrame, band: str, n: int = MAIN_WINDOW) -> list[str]:
    """Albums to draw for a band: at least MIN_SONGS songs, alphabetical, `non-album` last."""
    rows = summary[(summary["band"] == band) & (summary["n_window"] == n)].set_index("album")["songs"]
    albums = sorted(a for a in rows.index if a not in (BAND_TOTAL, NON_ALBUM) and rows[a] >= MIN_SONGS)
    if NON_ALBUM in rows.index and rows[NON_ALBUM] >= MIN_SONGS:
        albums.append(NON_ALBUM)
    return albums


def km_curve(curves: pd.DataFrame, band: str, album: str, n: int = MAIN_WINDOW) -> pd.DataFrame:
    """One Kaplan-Meier curve, starting at (0 shows, 1.0) when the mart does not include it."""
    c = curves[(curves["band"] == band) & (curves["album"] == album) & (curves["n_window"] == n)]
    c = c[["t_shows", "survival_probability", "ci_lower", "ci_upper"]].sort_values("t_shows")
    if len(c) and c["t_shows"].iloc[0] > 0:
        start = pd.DataFrame([{"t_shows": 0, "survival_probability": 1.0, "ci_lower": 1.0, "ci_upper": 1.0}])
        c = pd.concat([start, c], ignore_index=True)
    return c.reset_index(drop=True)


def album_table(summary: pd.DataFrame, band: str, n: int = MAIN_WINDOW) -> pd.DataFrame:
    """The album table of a band: songs, abandoned, censored, median; band total first.

    Columns: album, songs, abandoned, censored, median (NaN = not reached), small
    (fewer than MIN_SONGS songs), is_total.
    """
    rows = summary[(summary["band"] == band) & (summary["n_window"] == n)].copy()
    rows["is_total"] = rows["album"] == BAND_TOTAL
    rows["is_non_album"] = rows["album"] == NON_ALBUM
    rows = rows.sort_values(["is_total", "is_non_album", "album"], ascending=[False, True, True])
    rows = rows.rename(columns={"events": "abandoned", "median_survival_shows": "median"})
    rows["small"] = (rows["songs"] < MIN_SONGS) & ~rows["is_total"]
    return rows[["album", "songs", "abandoned", "censored", "median", "small", "is_total"]].reset_index(drop=True)


def median_table(summary: pd.DataFrame, bands: tuple[str, ...], n: int = MAIN_WINDOW) -> pd.DataFrame:
    """Band totals at one window, in band order. Columns: band, songs, abandoned, censored, median."""
    rows = summary[(summary["album"] == BAND_TOTAL) & (summary["n_window"] == n)].set_index("band")
    rows = rows.reindex(list(bands)).reset_index()
    rows = rows.rename(columns={"events": "abandoned", "median_survival_shows": "median"})
    return rows[["band", "songs", "abandoned", "censored", "median"]]


def sensitivity_table(summary: pd.DataFrame, bands: tuple[str, ...]) -> pd.DataFrame:
    """Median survival (shows) of each band's total at N = 25, 50 and 100. Columns: band, 25, 50, 100."""
    totals = summary[summary["album"] == BAND_TOTAL]
    wide = totals.pivot(index="band", columns="n_window", values="median_survival_shows")
    wide = wide.reindex(list(bands))[list(WINDOWS)].reset_index()
    wide.columns = ["band", *WINDOWS]
    return wide


def match_by_band(quality: pd.DataFrame, bands: tuple[str, ...]) -> pd.DataFrame:
    """Match quality per band, weighted by performances (the main metric).

    `rate` is matched performances over performances; `rate_album` weights the
    yearly share matched to a studio album by the year's performances.
    Columns: band, performances, matched, rate, rate_album, first_year, last_year.
    """
    q = quality.assign(album_matched=quality["match_rate_by_album"] * quality["performances"])
    g = q.groupby("band").agg(
        performances=("performances", "sum"), matched=("matched_performances", "sum"),
        album_matched=("album_matched", "sum"), first_year=("show_year", "min"), last_year=("show_year", "max"))
    g["rate"] = g["matched"] / g["performances"]
    g["rate_album"] = g["album_matched"] / g["performances"]
    return g.reindex(list(bands)).reset_index()[
        ["band", "performances", "matched", "rate", "rate_album", "first_year", "last_year"]]


def weakest_years(quality: pd.DataFrame, band: str, threshold: float = 0.90) -> pd.DataFrame:
    """Years of a band whose performance match rate is below `threshold` (the known-limitation cells)."""
    q = quality[(quality["band"] == band) & (quality["match_rate_by_performance"] < threshold)]
    return q[["show_year", "performances", "matched_performances", "match_rate_by_performance"]].sort_values(
        "show_year").reset_index(drop=True)


def shows_by_band(age: pd.DataFrame) -> pd.Series:
    """Distinct shows per band: the tour cells partition a band's shows, so their counts add up."""
    return age.groupby("band")["shows"].sum()


def touring_intensity(rot: pd.DataFrame, since: int = 2015) -> pd.Series:
    """Average show pairs per active year from `since` on (years with no pairs are not averaged)."""
    recent = rot[rot["show_year"] >= since]
    return recent.groupby("band")["pairs"].mean()


def final_survival(curves: pd.DataFrame, band: str, album: str = BAND_TOTAL, n: int = MAIN_WINDOW
                   ) -> tuple[int, float] | None:
    """Where a survival curve ends: (shows, share still in the setlist), or None without a curve."""
    c = km_curve(curves, band, album, n)
    if c.empty:
        return None
    last = c.iloc[-1]
    return int(last["t_shows"]), float(last["survival_probability"])


def survival_at(curves: pd.DataFrame, band: str, album: str, t: int, n: int = MAIN_WINDOW) -> tuple[float, int] | None:
    """Share still in the setlist at `t` shows and the songs still followed there, or None if the curve stops earlier."""
    c = curves[(curves["band"] == band) & (curves["album"] == album) & (curves["n_window"] == n)].sort_values("t_shows")
    if c.empty or t > c["t_shows"].max():
        return None
    row = c[c["t_shows"] <= t].iloc[-1] if (c["t_shows"] <= t).any() else None
    if row is None:
        return 1.0, int(c["at_risk"].iloc[0])
    return float(row["survival_probability"]), int(row["at_risk"])
