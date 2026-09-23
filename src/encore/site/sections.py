"""Chart and table builders shared by the comparison, band and home pages.

Each builder turns mart data into a `charts.Chart` (or table rows), taking every
word from the locale files through the translator. Colours follow the band, never
the rank; an album keeps the fixed palette order.
"""

from __future__ import annotations

import pandas as pd

from encore.site import bands as bands_mod
from encore.site import charts, i18n, shape, theme
from encore.site.charts import Chart, Curve, Series


def _band_series(names: tuple[str, ...], frame_for, y_column: str, thin: bool = False) -> list[Series]:
    """One `Series` per band that has data; `frame_for(band)` returns its yearly frame."""
    colors = theme.band_colors()
    series = []
    for name in names:
        d = frame_for(name)
        if d.empty:
            continue
        series.append(Series(name, colors[name], d["show_year"].astype(int).tolist(), d[y_column].tolist(),
                             d["thin"].tolist() if thin else []))
    return series


def age_chart(marts: dict[str, pd.DataFrame], names: tuple[str, ...], t: i18n.Translator, *, prefix: str,
              title: str, desc: str) -> Chart:
    """Repertoire age by year (weighted mean) for one or several bands."""
    series = _band_series(names, lambda b: shape.age_by_year(marts["mart_repertoire_age"], b), "avg_age")
    return charts.line_chart(series, title=title, desc=desc, ylabel=t.plain("chart.age_ylabel"), nf=t.number,
                             prefix=prefix, year_header=t.plain("chart.year"), decimals=1)


def rotation_chart(marts: dict[str, pd.DataFrame], names: tuple[str, ...], t: i18n.Translator, *, prefix: str,
                   title: str, desc: str, compact: bool = False) -> Chart:
    """Rotation by year (0-1) for one or several bands; thin years are hollow."""
    series = _band_series(names, lambda b: shape.rotation_by_year(marts["mart_band_rotation_by_year"], b),
                          "rotation", thin=True)
    return charts.line_chart(series, title=title, desc=desc, ylabel=t.plain("chart.rotation_ylabel"), nf=t.number,
                             prefix=prefix, year_header=t.plain("chart.year"), ylim=(-0.03, 1.03), decimals=2,
                             compact=compact, legend=not compact)


def tour_chart(marts: dict[str, pd.DataFrame], band: str, t: i18n.Translator, *, prefix: str, title: str,
               desc: str) -> Chart | None:
    """Median repertoire age of each tour-and-year cell for one band, or None if no cell qualifies."""
    cells = shape.age_by_tour_cell(marts["mart_repertoire_age"], band)
    if cells.empty:
        return None
    return charts.tour_median_bars(
        cells, color=theme.band_colors()[band], title=title, desc=desc, xlabel=t.plain("chart.tour_xlabel"),
        mean_label=t.plain("chart.mean"), nf=t.number, prefix=prefix,
        headers=[t.plain("chart.tour"), t.plain("chart.year"), t.plain("chart.shows"), t.plain("chart.median_age"), t.plain("chart.mean_age")])


def survival_chart(marts: dict[str, pd.DataFrame], band: str, t: i18n.Translator, *, prefix: str, title: str,
                   desc: str, n: int = shape.MAIN_WINDOW) -> Chart | None:
    """Kaplan-Meier curves by album (plus the band total, dashed), or None if no album is large enough."""
    summary, curves = marts["mart_survival_summary"], marts["mart_survival_curves"]
    albums = shape.survival_albums(summary, band, n)
    if not albums:
        return None
    sizes = summary[(summary["band"] == band) & (summary["n_window"] == n)].set_index("album")["songs"]
    drawn = [Curve(f"{a} ({t.plain('chart.songs_n', n=int(sizes[a]))})", charts.album_color(i, a), shape.km_curve(curves, band, a, n))
             for i, a in enumerate(albums)]
    total = shape.km_curve(curves, band, shape.BAND_TOTAL, n)
    if len(total):
        drawn.append(Curve(f"{t.plain('chart.all_songs')} ({t.plain('chart.songs_n', n=int(sizes[shape.BAND_TOTAL]))})",
                           theme.LIGHT["ink"], total, dashed=True))
    return charts.km_chart(
        drawn, title=title, desc=desc, xlabel=t.plain("chart.survival_xlabel"), ylabel=t.plain("chart.survival_ylabel"),
        median_label=t.plain("chart.median"), nf=t.number, prefix=prefix, first_header=t.plain("chart.album"),
        t_header=t.plain("chart.t_header"))


def survival_totals_rows(marts: dict[str, pd.DataFrame], names: tuple[str, ...], t: i18n.Translator, locale: str,
                         band_cell, n: int = shape.MAIN_WINDOW) -> dict:
    """Band totals at window N: songs, abandoned, censored and median survival, in band order."""
    table = shape.median_table(marts["mart_survival_summary"], names, n)
    headers = [t.plain("labels.band"), t.plain("labels.songs"), t.plain("labels.abandoned"), t.plain("labels.censored"),
               t.plain("labels.median_shows")]
    rows = []
    for _, r in table.iterrows():
        median = t.plain("labels.not_reached") if pd.isna(r["median"]) else t.number(r["median"])
        rows.append([band_cell(r["band"], locale), t.number(r["songs"]), t.number(r["abandoned"]),
                     t.number(r["censored"]), median])
    return {"headers": headers, "rows": rows}


def album_rows(marts: dict[str, pd.DataFrame], band: str, t: i18n.Translator, n: int = shape.MAIN_WINDOW) -> dict:
    """The album table of a band: total first, small albums flagged with an asterisk."""
    table = shape.album_table(marts["mart_survival_summary"], band, n)
    headers = [t.plain("chart.album"), t.plain("labels.songs"), t.plain("labels.abandoned"), t.plain("labels.censored"),
               t.plain("labels.median_shows")]
    rows = []
    for _, r in table.iterrows():
        name = t.plain("chart.all_songs") if r["is_total"] else r["album"] + (" *" if r["small"] else "")
        median = t.plain("labels.not_reached") if pd.isna(r["median"]) else t.number(r["median"])
        rows.append([name, t.number(r["songs"]), t.number(r["abandoned"]), t.number(r["censored"]), median])
    return {"headers": headers, "rows": rows}


def band_facts(marts: dict[str, pd.DataFrame], band: str) -> dict[str, object]:
    """Numbers for a band's header chips and the home index: years, shows, match rate, median survival."""
    quality = marts["mart_match_quality"]
    q = quality[quality["band"] == band]
    shows = shape.shows_by_band(marts["mart_repertoire_age"]).get(band, 0)
    match = shape.match_by_band(quality, (band,)).iloc[0]
    totals = shape.median_table(marts["mart_survival_summary"], (band,)).iloc[0]
    return {"first_year": int(q["show_year"].min()), "last_year": int(q["show_year"].max()), "shows": int(shows),
            "match": float(match["rate"]), "median": totals["median"], "slug": bands_mod.slug(band)}
