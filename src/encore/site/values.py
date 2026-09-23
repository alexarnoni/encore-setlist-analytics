"""Placeholder values for the hand-written text, filled from the marts at build time (R4).

A number that has no value is left out of the dictionary, so a text that uses it
fails the build instead of printing a blank or a stale figure.
"""

from __future__ import annotations

import re

import pandas as pd

from encore.site import bands as bands_mod
from encore.site import shape
from encore.site.i18n import fmt_number, fmt_percent


def placeholder_values(marts: dict[str, pd.DataFrame], bands: tuple[str, ...], locale: str) -> dict[str, str]:
    """Return `{placeholder: formatted text}` for `locale`.

    Per band (key prefix from `bands.key`): `_median`, `_songs`, `_abandoned`,
    `_censored` (band total at N = 50), `_shows`, `_first_year`, `_last_year`
    and `_match` (share of performances matched to the catalog). Global:
    `bands_count`, `shows_total`, `band_list`. Also per band `_pairs_avg` and
    `_pairs_max` (show pairs per year), per band-and-year `<band>_<year>_performances`,
    `_matched`, `_rate`, and `<band>_weak_share` (share of performances in years
    below 90% match), which only exists for a band that has such years.
    """
    values: dict[str, str] = {}
    totals = shape.median_table(marts["mart_survival_summary"], bands).set_index("band")
    match = shape.match_by_band(marts["mart_match_quality"], bands).set_index("band")
    shows = shape.shows_by_band(marts["mart_repertoire_age"])

    for band in bands:
        k = bands_mod.key(band)
        row = totals.loc[band]
        for column, name in (("median", "median"), ("songs", "songs"), ("abandoned", "abandoned"),
                             ("censored", "censored")):
            if pd.notna(row[column]):
                values[f"{k}_{name}"] = fmt_number(float(row[column]), 0, locale)
        if band in shows.index:
            values[f"{k}_shows"] = fmt_number(float(shows[band]), 0, locale)
        if pd.notna(match.loc[band, "rate"]):
            values[f"{k}_match"] = fmt_percent(float(match.loc[band, "rate"]), 1, locale)
            values[f"{k}_first_year"] = str(int(match.loc[band, "first_year"]))
            values[f"{k}_last_year"] = str(int(match.loc[band, "last_year"]))

    _add_touring_and_weak_cells(values, marts, bands, locale)
    add_findings_values(values, marts, bands, locale)
    values["bands_count"] = str(len(bands))
    values["band_list"] = ", ".join(bands)
    values["shows_total"] = fmt_number(float(shows.sum()), 0, locale)
    return values


# Bands behind the home page's featured charts.
FEATURED_AGE_BANDS = ("Metallica", "Avenged Sevenfold", "Linkin Park")
HERO_SURVIVAL_BAND = "Oasis"

WEAK_MATCH_RATE = 0.90
TOURING_SINCE = 2015


def _add_touring_and_weak_cells(values: dict[str, str], marts: dict[str, pd.DataFrame], bands: tuple[str, ...],
                                locale: str) -> None:
    """Touring intensity and per band-and-year match cells, for the methodology text."""
    rot = marts["mart_band_rotation_by_year"]
    average = shape.touring_intensity(rot, since=TOURING_SINCE)
    peak = rot.groupby("band")["pairs"].max()
    quality = marts["mart_match_quality"]
    for band in bands:
        k = bands_mod.key(band)
        if band in average.index:
            values[f"{k}_pairs_avg"] = fmt_number(round(float(average[band])), 0, locale)
        if band in peak.index:
            values[f"{k}_pairs_max"] = fmt_number(float(peak[band]), 0, locale)
        rows = quality[quality["band"] == band]
        for row in rows.itertuples():
            cell = f"{k}_{int(row.show_year)}"
            values[f"{cell}_performances"] = fmt_number(float(row.performances), 0, locale)
            values[f"{cell}_matched"] = fmt_number(float(row.matched_performances), 0, locale)
            values[f"{cell}_rate"] = fmt_percent(float(row.match_rate_by_performance), 1, locale)
        weak = rows[rows["match_rate_by_performance"] < WEAK_MATCH_RATE]
        if len(weak) and rows["performances"].sum() > 0:
            share = float(weak["performances"].sum() / rows["performances"].sum())
            values[f"{k}_weak_share"] = fmt_percent(share, 2, locale)


# One-year dips in repertoire age that the findings text talks about: id -> (band, year before,
# year at the low point, year after). The album behind each dip is named in the hand-written text;
# the marts carry no album release dates.
DIPS: dict[str, tuple[str, int, int, int]] = {
    "metallica_death_magnetic": ("Metallica", 2007, 2009, 2010),
    "metallica_hardwired": ("Metallica", 2015, 2018, 2019),
    "metallica_72_seasons": ("Metallica", 2022, 2023, 2025),
    "avenged_nightmare": ("Avenged Sevenfold", 2009, 2010, 2011),
    "avenged_hail_to_the_king": ("Avenged Sevenfold", 2012, 2013, 2014),
    "avenged_the_stage": ("Avenged Sevenfold", 2015, 2016, 2017),
    "linkin_minutes_to_midnight": ("Linkin Park", 2006, 2007, 2008),
    "linkin_a_thousand_suns": ("Linkin Park", 2009, 2010, 2011),
    "linkin_living_things": ("Linkin Park", 2011, 2012, 2013),
}
MIN_GAP_YEARS = 3

# Names produced by `add_findings_values`: the hand-written findings quote these specific
# figures of the real data. Tests that render fake marts fill only names that match this pattern.
FINDINGS_KEY = re.compile(r"^(dip_.+|[a-z0-9_]+_(age|rot|tour|album|gap|final)(_.+)?)$")


def add_findings_values(values: dict[str, str], marts: dict[str, pd.DataFrame], bands: tuple[str, ...],
                        locale: str) -> None:
    """Numbers the hand-written findings quote. A figure that does not exist is left out.

    Per band `<k>` (see `bands.key`), all formatted for `locale`:
    `<k>_age_<year>` (repertoire age), `<k>_age_first/_age_first_year/_age_last/_age_last_year`,
    `<k>_gap_from/_gap_to` (the longest break of 3+ years between years with shows, if any),
    `<k>_rot_<year>` (rotation of years with 5+ show pairs), `<k>_rot_first3/_rot_last3` and
    `<k>_rot_first3_from/_to`, `<k>_rot_last3_from/_to` (mean rotation of the first and last three
    such years), `<k>_tour_<tour>_rotation` and `_shows`, `<k>_final/_final_t` (where the all-songs
    survival curve ends), `<k>_album_<album>_songs/_abandoned/_censored/_median/_final/_final_t`
    (albums with 5+ songs), and `dip_<id>_before/_low/_after/_size` for `DIPS`.
    """
    age, rot = marts["mart_repertoire_age"], marts["mart_band_rotation_by_year"]
    tours, curves, summary = marts["mart_tour_rotation"], marts["mart_survival_curves"], marts["mart_survival_summary"]

    for band in bands:
        k = bands_mod.key(band)
        yearly = shape.age_by_year(age, band)
        for year, value in zip(yearly["show_year"], yearly["avg_age"]):
            values[f"{k}_age_{int(year)}"] = fmt_number(float(value), 1, locale)
        if len(yearly):
            first, last = yearly.iloc[0], yearly.iloc[-1]
            values.update({
                f"{k}_age_first": fmt_number(float(first["avg_age"]), 1, locale),
                f"{k}_age_first_year": str(int(first["show_year"])),
                f"{k}_age_last": fmt_number(float(last["avg_age"]), 1, locale),
                f"{k}_age_last_year": str(int(last["show_year"]))})
            years = [int(y) for y in yearly["show_year"]]
            gaps = [(b - a, a, b) for a, b in zip(years, years[1:]) if b - a >= MIN_GAP_YEARS]
            if gaps:
                _, start, end = max(gaps)
                values[f"{k}_gap_from"], values[f"{k}_gap_to"] = str(start), str(end)

        reliable = shape.rotation_by_year(rot, band)
        reliable = reliable[~reliable["thin"]]
        for year, value in zip(reliable["show_year"], reliable["rotation"]):
            values[f"{k}_rot_{int(year)}"] = fmt_number(float(value), 2, locale)
        if len(reliable) >= 3:
            head, tail = reliable.head(3), reliable.tail(3)
            values.update({
                f"{k}_rot_first3": fmt_number(float(head["rotation"].mean()), 2, locale),
                f"{k}_rot_last3": fmt_number(float(tail["rotation"].mean()), 2, locale),
                f"{k}_rot_first3_from": str(int(head["show_year"].min())),
                f"{k}_rot_first3_to": str(int(head["show_year"].max())),
                f"{k}_rot_last3_from": str(int(tail["show_year"].min())),
                f"{k}_rot_last3_to": str(int(tail["show_year"].max()))})

        for row in tours[tours["band"] == band].itertuples():
            tour = f"{k}_tour_{bands_mod.key(row.tour_name)}"
            values[f"{tour}_rotation"] = fmt_number(float(row.rotation), 2, locale)
            values[f"{tour}_shows"] = fmt_number(float(row.shows), 0, locale)

        end = shape.final_survival(curves, band)
        if end:
            values[f"{k}_final_t"], values[f"{k}_final"] = fmt_number(end[0], 0, locale), fmt_percent(end[1], 0, locale)
        table = shape.album_table(summary, band).set_index("album")
        for album in shape.survival_albums(summary, band):
            row = table.loc[album]
            ak = f"{k}_album_{bands_mod.key(album)}"
            values.update({f"{ak}_songs": fmt_number(float(row["songs"]), 0, locale),
                           f"{ak}_abandoned": fmt_number(float(row["abandoned"]), 0, locale),
                           f"{ak}_censored": fmt_number(float(row["censored"]), 0, locale)})
            if pd.notna(row["median"]):
                values[f"{ak}_median"] = fmt_number(float(row["median"]), 0, locale)
            album_end = shape.final_survival(curves, band, album)
            if album_end:
                values[f"{ak}_final_t"] = fmt_number(album_end[0], 0, locale)
                values[f"{ak}_final"] = fmt_percent(album_end[1], 0, locale)

    for dip_id, (band, before, low, after) in DIPS.items():
        series = shape.age_by_year(age, band).set_index("show_year")["avg_age"]
        if not all(year in series.index for year in (before, low, after)):
            continue
        b, lo, af = (round(float(series[year]), 1) for year in (before, low, after))
        values.update({
            f"dip_{dip_id}_before": fmt_number(b, 1, locale), f"dip_{dip_id}_low": fmt_number(lo, 1, locale),
            f"dip_{dip_id}_after": fmt_number(af, 1, locale),
            # Rounded ends again, so the printed size equals the printed difference.
            f"dip_{dip_id}_size": fmt_number(round(b - lo, 1), 1, locale)})
