"""The page registry and what each page's template receives.

Pages are addressed by a locale-independent path (`""`, `comparison/`,
`bands/muse/`); `href` puts a locale prefix in front. Layout data (navigation,
language switch, hreflang alternates, page title) is built here so the base
template stays free of logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
from markupsafe import Markup, escape

from encore.site import bands as bands_mod
from encore.site import i18n, sections, shape, theme, values


@dataclass(frozen=True)
class Page:
    """One page of the site, identical in structure across locales."""

    key: str  # home, comparison, methodology, about, band
    path: str  # "", "comparison/", "bands/muse/"
    template: str
    band: str | None = None


def page_list(bands: tuple[str, ...]) -> list[Page]:
    """Every page of one locale: the four fixed pages, then one page per band."""
    fixed = [
        Page("home", "", "home.html"),
        Page("comparison", "comparison/", "comparison.html"),
        Page("methodology", "methodology/", "methodology.html"),
        Page("about", "about/", "about.html"),
    ]
    return fixed + [Page("band", f"bands/{bands_mod.slug(b)}/", "band.html", band=b) for b in bands]


def href(locale: str, path: str) -> str:
    """Root-relative URL of a page in a locale."""
    return f"/{i18n.URL_PREFIX[locale]}/{path}"


def layout(page: Page, locale: str, pages: list[Page], t: i18n.Translator, origin: str) -> dict[str, Any]:
    """Header navigation, language switch, `<title>`, canonical and hreflang data for one page."""
    nav = [
        {"label": t("nav.bands"), "href": href(locale, "#bands"), "current": page.key == "band"},
        {"label": t("nav.comparison"), "href": href(locale, "comparison/"), "current": page.key == "comparison"},
        {"label": t("nav.methodology"), "href": href(locale, "methodology/"), "current": page.key == "methodology"},
        {"label": t("nav.about"), "href": href(locale, "about/"), "current": page.key == "about"},
    ]
    switch = [
        {"locale": loc, "label": t(f"lang.{loc}"), "name": t(f"lang.{loc}_name"),
         "href": href(loc, page.path), "current": loc == locale}
        for loc in i18n.LOCALES
    ]
    alternates = [(loc, origin + href(loc, page.path)) for loc in i18n.LOCALES]
    alternates.append(("x-default", origin + href(i18n.DEFAULT_LOCALE, page.path)))
    page_title = page.band if page.band else t(f"{page.key}.title")
    return {
        "nav": nav, "switch": switch, "alternates": alternates, "home_href": href(locale, ""),
        "canonical": origin + href(locale, page.path), "page_title": page_title,
        "title": page_title if page.key == "home" else f"{page_title} · {t('site.name')}",
    }


def band_cell(band: str, locale: str, link: bool = True) -> Markup:
    """Table cell content for a band: its colour swatch and its name, linked to its page."""
    swatch = Markup('<span class="swatch" style="background: var({})"></span>').format(theme.band_token(band))
    name = escape(band)
    if link:
        name = Markup('<a href="{}">{}</a>').format(href(locale, f"bands/{bands_mod.slug(band)}/"), band)
    return swatch + name


def _median_text(value: float, t: i18n.Translator) -> str:
    return t("labels.not_reached") if pd.isna(value) else t.number(value)


def sensitivity_table(marts: dict[str, pd.DataFrame], bands: tuple[str, ...], locale: str, t: i18n.Translator) -> dict:
    """Median survival by band at each window (N sensitivity table)."""
    wide = shape.sensitivity_table(marts["mart_survival_summary"], bands)
    headers = [t("labels.band"), *[t("labels.n_col", n=n) for n in shape.WINDOWS]]
    rows = [[band_cell(r["band"], locale), *[_median_text(r[n], t) for n in shape.WINDOWS]]
            for _, r in wide.iterrows()]
    return {"headers": headers, "rows": rows}


def match_table(marts: dict[str, pd.DataFrame], bands: tuple[str, ...], locale: str, t: i18n.Translator) -> dict:
    """Catalog match quality by band: main measure (performances) and secondary (album)."""
    m = shape.match_by_band(marts["mart_match_quality"], bands)
    headers = [t("labels.band"), t("labels.performances"), t("labels.matched_rate"),
               t("labels.album_rate"), t("labels.years")]
    rows = [[band_cell(r["band"], locale), t.number(r["performances"]), t.percent(r["rate"], 1),
             t.percent(r["rate_album"], 1), f"{int(r['first_year'])}–{int(r['last_year'])}"]
            for _, r in m.iterrows()]
    return {"headers": headers, "rows": rows}


def band_findings(band: str, t: i18n.Translator) -> dict[str, Any]:
    """A band's findings in three layers: a plain lead, the key numbers, and the caveats (band-specific, then common)."""
    k = bands_mod.key(band)
    extra = {"min_pairs": shape.MIN_PAIRS}
    caveats = [*t.section(f"findings.{k}.caveats", **extra), t("findings.common", **extra)]
    return {"lead": t(f"findings.{k}.lead"), "numbers": t(f"findings.{k}.numbers"), "caveats": caveats}


def band_context(band: str, *, locale: str, t: i18n.Translator, marts: dict[str, pd.DataFrame],
                 bands: tuple[str, ...]) -> dict[str, Any]:
    """Everything a band page shows: header chips, findings, four charts, album table, other bands."""
    facts = sections.band_facts(marts, band)
    chips = [t("band.chip_years", first=facts["first_year"], last=facts["last_year"]),
             t("band.chip_shows", n=t.number(facts["shows"])),
             t("band.chip_match", pct=t.percent(facts["match"], 1))]
    if pd.notna(facts["median"]):
        chips.append(t("band.chip_median", n=t.number(facts["median"])))
    slug = bands_mod.slug(band)
    kw = {"band": band}

    def chart_text(section: str) -> dict[str, str]:
        return {"title": t.plain(f"band.{section}.title", **kw), "desc": t.plain(f"band.{section}.desc", **kw)}

    albums = sections.album_rows(marts, band, t)
    album_table = shape.album_table(marts["mart_survival_summary"], band)
    return {
        "band_token": theme.band_token(band),
        "chips": chips,
        "findings": band_findings(band, t),
        "charts": {
            "age": sections.age_chart(marts, (band,), t, prefix=f"{slug}-age", **chart_text("age")),
            "tours": sections.tour_chart(marts, band, t, prefix=f"{slug}-tours", **chart_text("tours")),
            "rotation": sections.rotation_chart(marts, (band,), t, prefix=f"{slug}-rot", **chart_text("rotation")),
            "survival": sections.survival_chart(marts, band, t, prefix=f"{slug}-km", **chart_text("survival")),
        },
        "albums": albums,
        "has_small_albums": bool(album_table["small"].any()),
        "ci_shown": sections.show_ci(len(shape.survival_albums(marts["mart_survival_summary"], band))),
        "others": [{"name": b, "href": href(locale, f"bands/{bands_mod.slug(b)}/"), "token": theme.band_token(b)}
                   for b in bands if b != band],
    }


def home_context(*, locale: str, t: i18n.Translator, marts: dict[str, pd.DataFrame],
                 bands: tuple[str, ...]) -> dict[str, Any]:
    """Home page: three findings (two hero stats and a set of small multiples) and the band index."""
    featured = tuple(b for b in values.FEATURED_AGE_BANDS if b in bands)
    f1 = sections.age_chart(marts, featured, t, prefix="home-age", title=t.plain("home.f1.title"),
                            desc=t.plain("home.f1.desc"))
    panels = []
    for band in bands:
        slug = bands_mod.slug(band)
        chart = sections.rotation_chart(
            marts, (band,), t, prefix=f"home-rot-{slug}", compact=True,
            title=t.plain("home.f2.cell_title", band=band), desc=t.plain("home.f2.cell_desc", band=band))
        panels.append({"band": band, "href": href(locale, f"bands/{slug}/"), "token": theme.band_token(band),
                       "chart": chart})
    # One combined table is the text alternative for all the panels (the SVG of this chart is not shown).
    rotation_table = sections.rotation_chart(marts, bands, t, prefix="home-rot-all", title="", desc="")
    f3 = sections.survival_chart(marts, values.HERO_SURVIVAL_BAND, t, prefix="home-km",
                                 title=t.plain("home.f3.title"), desc=t.plain("home.f3.desc"))
    facts = {b: sections.band_facts(marts, b) for b in bands}
    headers = [t("labels.band"), t("labels.years"), t("chart.shows"), t("labels.matched_rate"), t("labels.median_shows")]
    rows = []
    for band in bands:
        f = facts[band]
        median = t("labels.not_reached") if pd.isna(f["median"]) else t.number(f["median"])
        rows.append([band_cell(band, locale), f"{f['first_year']}–{f['last_year']}", t.number(f["shows"]),
                     t.percent(f["match"], 1), median])
    return {"charts": {"f1": f1, "f3": f3}, "rotation_panels": panels, "rotation_table": rotation_table,
            "index": {"headers": headers, "rows": rows}}


def context(page: Page, *, locale: str, t: i18n.Translator, marts: dict[str, pd.DataFrame],
            bands: tuple[str, ...]) -> dict[str, Any]:
    """Page-specific template variables (grows as page content is added)."""
    ctx: dict[str, Any] = {"t": t, "locale": locale, "lang": locale, "page": page, "band": page.band,
                           "bands": bands, "band_slug": bands_mod.slug(page.band) if page.band else None}
    ctx["min_pairs"], ctx["min_songs"] = shape.MIN_PAIRS, shape.MIN_SONGS
    ctx["min_tour_shows"], ctx["n_window"] = shape.MIN_TOUR_CELL_SHOWS, shape.MAIN_WINDOW
    if page.band:
        ctx.update(band_context(page.band, locale=locale, t=t, marts=marts, bands=bands))
    if page.key == "home":
        ctx.update(home_context(locale=locale, t=t, marts=marts, bands=bands))
    if page.key == "comparison":
        ctx["charts"] = {
            "age": sections.age_chart(marts, bands, t, prefix="cmp-age", title=t.plain("comparison.age.title"),
                                      desc=t.plain("comparison.age.desc")),
            "rotation": sections.rotation_chart(marts, bands, t, prefix="cmp-rot",
                                                title=t.plain("comparison.rotation.title"),
                                                desc=t.plain("comparison.rotation.desc")),
        }
        ctx["survival"] = sections.survival_totals_rows(marts, bands, t, locale, band_cell)
    if page.key == "methodology":
        ctx["sensitivity"] = sensitivity_table(marts, bands, locale, t)
        ctx["match"] = match_table(marts, bands, locale, t)
    return ctx
