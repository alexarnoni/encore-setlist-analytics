"""Charts as inline SVG (matplotlib), themed through CSS custom properties.

Each function draws with the light-theme token values as sentinels, then
`finalize_svg` rewrites every colour to `var(--token)`, so the page's theme
toggle recolours charts with no re-render and no JavaScript. Text stays text
(`svg.fonttype: none`), sized in the page's mono font, and every chart returns a
data table so the page has a text alternative (R6.3).

All words in a chart (axis labels, legend entries, table headers, the median
label) are passed in by the caller from the locale files; nothing is hardcoded.
"""

from __future__ import annotations

import io
import math
import re
from dataclasses import dataclass, field
from html import escape
from typing import Callable

import numpy as np
import pandas as pd
from matplotlib import rc_context
from matplotlib.figure import Figure
from matplotlib.ticker import MaxNLocator

from encore.site import theme

NumberFormat = Callable[[float, int], str]

INK, MUTED, LINE, NEUTRAL, CARD = (theme.LIGHT[k] for k in ("ink", "muted", "line", "neutral", "card"))
ALBUM_PALETTE = theme.BAND_PALETTE
DASH = "–"

RC = {
    "svg.fonttype": "none", "svg.hashsalt": "encore-site",
    "font.family": "DejaVu Sans Mono", "font.size": 9,
    "figure.facecolor": "none", "axes.facecolor": "none", "savefig.facecolor": "none",
    "axes.edgecolor": LINE, "axes.labelcolor": MUTED, "text.color": INK,
    "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": LINE, "grid.linewidth": 0.8, "axes.axisbelow": True,
    "legend.frameon": False, "legend.fontsize": 8,
}


@dataclass(frozen=True)
class Chart:
    """A rendered chart: inline SVG plus the table that is its text alternative."""

    svg: str
    headers: list[str]
    rows: list[list[str]]


@dataclass(frozen=True)
class Series:
    """One line of a yearly chart. `thin[i]` marks a year with too little data (hollow marker)."""

    name: str
    color: str
    xs: list[int]
    ys: list[float]
    thin: list[bool] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.thin:
            object.__setattr__(self, "thin", [False] * len(self.xs))


@dataclass(frozen=True)
class Curve:
    """One Kaplan-Meier curve with its label and colour."""

    label: str
    color: str
    data: pd.DataFrame
    dashed: bool = False


_HEX = re.compile(r"#[0-9a-fA-F]{6}\b")
_FONT = re.compile(r"font: (\d+(?:\.\d+)?)px '[^']*'")


def finalize_svg(raw: str, *, title: str, desc: str, prefix: str) -> str:
    """Turn matplotlib's SVG into an inline, themeable, accessible fragment.

    Removes the XML prolog, metadata and fixed size; prefixes every id so several
    charts can share a page; maps colours to CSS custom properties; sets the font
    to the page's mono stack; adds `role="img"`, `<title>` and `<desc>`.
    """
    svg = raw[raw.index("<svg"):]
    svg = re.sub(r"<metadata>.*?</metadata>", "", svg, flags=re.S)
    ids = set(re.findall(r'\bid="([^"]+)"', svg))
    for old in sorted(ids, key=len, reverse=True):
        svg = svg.replace(f'id="{old}"', f'id="{prefix}-{old}"')
        svg = svg.replace(f"url(#{old})", f"url(#{prefix}-{old})")
        svg = svg.replace(f'href="#{old}"', f'href="#{prefix}-{old}"')
    mapping = theme.sentinel_map()

    def colour(match: re.Match[str]) -> str:
        token = mapping.get(match.group(0).lower())
        return f"var({token})" if token else match.group(0)

    svg = _HEX.sub(colour, svg)
    svg = _FONT.sub(r"font-size: \1px; font-family: var(--font-mono)", svg)

    def open_tag(match: re.Match[str]) -> str:
        tag = re.sub(r'\s(width|height)="[^"]*"', "", match.group(0))
        return (f'{tag[:-1]} role="img" aria-labelledby="{prefix}-title {prefix}-desc" '
                f'class="chart-svg">'
                f'<title id="{prefix}-title">{escape(title)}</title>'
                f'<desc id="{prefix}-desc">{escape(desc)}</desc>')

    return re.sub(r"<svg\b[^>]*>", open_tag, svg, count=1)


def _render(fig: Figure, *, title: str, desc: str, prefix: str) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="svg", bbox_inches="tight", pad_inches=0.05, metadata={"Date": None})
    return finalize_svg(buf.getvalue().decode("utf8"), title=title, desc=desc, prefix=prefix)


def _year_axis(ax) -> None:
    ax.xaxis.set_major_locator(MaxNLocator(nbins=5, integer=True))
    ax.ticklabel_format(useOffset=False, axis="x")


def line_chart(
    series: list[Series], *, title: str, desc: str, ylabel: str, nf: NumberFormat, prefix: str,
    year_header: str, ylim: tuple[float, float] | None = None, decimals: int = 1,
    compact: bool = False, legend: bool = True,
) -> Chart:
    """Values by year for one or several bands; thin years are hollow and left out of the line."""
    size = (2.0, 1.5) if compact else (5.4, 3.2)
    ms, lw = (3, 1.4) if compact else (5, 2)
    with rc_context(RC):
        fig = Figure(figsize=size)
        ax = fig.subplots()
        handles = []
        for s in series:
            values = dict(zip(s.xs, s.ys))
            thin = dict(zip(s.xs, s.thin))
            years = list(range(min(s.xs), max(s.xs) + 1))
            solid = [values[x] if x in values and not thin[x] else math.nan for x in years]
            (line,) = ax.plot(years, solid, color=s.color, linewidth=lw, marker="o", markersize=ms,
                              markeredgecolor=CARD, markeredgewidth=1, label=s.name)
            handles.append(line)
            hollow = [x for x in s.xs if thin[x]]
            if hollow:
                ax.plot(hollow, [values[x] for x in hollow], linestyle="none", marker="o", markersize=ms,
                        markerfacecolor=CARD, markeredgecolor=s.color, markeredgewidth=1.4)
        if ylim:
            ax.set_ylim(*ylim)
        _year_axis(ax)
        if compact:
            ax.yaxis.set_major_locator(MaxNLocator(nbins=3))
            ax.tick_params(labelsize=7, pad=2)
            ax.xaxis.set_major_locator(MaxNLocator(nbins=3, integer=True))
        else:
            ax.set_ylabel(ylabel)
        if legend and len(series) > 1:
            fig.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, 0.0), ncol=4,
                       columnspacing=1.2, handlelength=1.4)
        svg = _render(fig, title=title, desc=desc, prefix=prefix)

    all_years = sorted({x for s in series for x in s.xs})
    lookup = [(dict(zip(s.xs, s.ys)), dict(zip(s.xs, s.thin))) for s in series]
    rows = []
    for year in all_years:
        row = [str(year)]
        for values, thin in lookup:
            row.append(DASH if year not in values else nf(values[year], decimals) + ("*" if thin[year] else ""))
        rows.append(row)
    return Chart(svg, [year_header, *[s.name for s in series]], rows)


def _short(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def tour_median_bars(
    cells: pd.DataFrame, *, color: str, title: str, desc: str, xlabel: str, mean_label: str,
    nf: NumberFormat, prefix: str, headers: list[str],
) -> Chart:
    """Median repertoire age per tour-and-year cell (bars), with the mean as a marker.

    `cells` has columns tour_name, show_year, shows, median_age, avg_age, oldest first.
    """
    n = len(cells)
    labels = [f"{_short(t, 28)} {y}" for t, y in zip(cells["tour_name"], cells["show_year"])]
    with rc_context(RC):
        fig = Figure(figsize=(5.4, 0.8 + 0.22 * n))
        ax = fig.subplots()
        pos = np.arange(n)
        ax.barh(pos, cells["median_age"], color=color, height=0.62)
        ax.scatter(cells["avg_age"], pos, marker="D", s=12, color=INK, zorder=3, label=mean_label)
        ax.set_yticks(pos, labels)
        ax.invert_yaxis()
        ax.set_ylim(n - 0.4, -0.6)
        ax.grid(axis="y", visible=False)
        ax.set_xlabel(xlabel)
        ax.legend(loc="upper right", handletextpad=0.3)
        svg = _render(fig, title=title, desc=desc, prefix=prefix)
    rows = [
        [t, str(y), nf(s, 0), nf(m, 0), nf(a, 1)]
        for t, y, s, m, a in zip(cells["tour_name"], cells["show_year"], cells["shows"],
                                 cells["median_age"], cells["avg_age"])
    ]
    return Chart(svg, headers, rows)


def _survival_at(curve: pd.DataFrame, t: int) -> float | None:
    """Survival probability at t shows (step function), or None beyond the curve's last time."""
    if curve.empty or t > curve["t_shows"].max():
        return None
    return float(curve[curve["t_shows"] <= t]["survival_probability"].iloc[-1])


def km_chart(
    curves: list[Curve], *, title: str, desc: str, xlabel: str, ylabel: str, median_label: str,
    nf: NumberFormat, prefix: str, first_header: str, t_header: str,
    checkpoints: tuple[int, ...] = (25, 50, 100, 200, 400), show_ci: bool = True,
) -> Chart:
    """Share of songs still in the setlist after t shows, one step curve per album."""
    with rc_context(RC):
        fig = Figure(figsize=(5.4, 3.4))
        ax = fig.subplots()
        for c in curves:
            d = c.data
            if show_ci and not c.dashed:
                ax.fill_between(d["t_shows"], d["ci_lower"], d["ci_upper"], step="post", color=c.color,
                                alpha=0.05, linewidth=0)
            ax.step(d["t_shows"], d["survival_probability"], where="post", color=c.color,
                    linewidth=1.8, linestyle="--" if c.dashed else "-", label=c.label)
        ax.axhline(0.5, color=NEUTRAL, linewidth=0.8)
        ax.text(1.0, 0.5, f"{median_label} ", transform=ax.get_yaxis_transform(), ha="right", va="bottom",
                fontsize=7, color=MUTED)
        ax.set_ylim(0, 1.02)
        ax.set_xlim(left=0)
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        ncol = 1 if max(len(c.label) for c in curves) > 26 else 2
        fig.legend(loc="upper center", bbox_to_anchor=(0.5, 0.0), ncol=ncol, columnspacing=1.4, handlelength=1.6)
        svg = _render(fig, title=title, desc=desc, prefix=prefix)
    rows = []
    for c in curves:
        row = [c.label]
        for t in checkpoints:
            v = _survival_at(c.data, t)
            row.append(DASH if v is None else nf(v * 100, 0) + "%")
        rows.append(row)
    return Chart(svg, [first_header, *[t_header.format(t=t) for t in checkpoints]], rows)


def album_color(index: int, album: str, non_album: str = "non-album") -> str:
    """Colour of an album curve: the fixed palette in order, grey for `non-album`."""
    return NEUTRAL if album == non_album else ALBUM_PALETTE[index % len(ALBUM_PALETTE)]
