"""Placeholder values for the hand-written text, filled from the marts at build time (R4).

A number that has no value is left out of the dictionary, so a text that uses it
fails the build instead of printing a blank or a stale figure.
"""

from __future__ import annotations

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
    _add_headline_values(values, marts, locale)
    values["bands_count"] = str(len(bands))
    values["band_list"] = ", ".join(bands)
    values["shows_total"] = fmt_number(float(shows.sum()), 0, locale)
    return values


# Bands behind the home page's featured charts and hero stats.
FEATURED_AGE_BANDS = ("Metallica", "Avenged Sevenfold", "Linkin Park")
HERO_AGE_BAND = "Metallica"
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


def _add_headline_values(values: dict[str, str], marts: dict[str, pd.DataFrame], locale: str) -> None:
    """Numbers behind the home page's hero stats.

    f1_*: the biggest one-year fall in the hero band's repertoire age (f1_year_prev, f1_year,
    f1_from, f1_to, f1_drop). f3_*: where the hero band's all-songs survival curve ends
    (f3_t shows, f3_stat share still played). Left out when the data has no such figure.
    """
    drop = shape.largest_age_drop(marts["mart_repertoire_age"], HERO_AGE_BAND)
    if drop:
        values.update(
            f1_year_prev=str(int(drop["year_prev"])), f1_year=str(int(drop["year"])),
            f1_from=fmt_number(drop["age_from"], 1, locale), f1_to=fmt_number(drop["age_to"], 1, locale),
            # From the rounded ends, so the printed difference matches the printed numbers.
            f1_drop=fmt_number(round(drop["age_from"], 1) - round(drop["age_to"], 1), 1, locale))
    end = shape.final_survival(marts["mart_survival_curves"], HERO_SURVIVAL_BAND)
    if end:
        values.update(f3_t=fmt_number(end[0], 0, locale), f3_stat=fmt_percent(end[1], 0, locale))
