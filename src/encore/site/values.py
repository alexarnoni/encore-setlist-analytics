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
    `bands_count`, `shows_total`.
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

    values["bands_count"] = str(len(bands))
    values["shows_total"] = fmt_number(float(shows.sum()), 0, locale)
    return values
