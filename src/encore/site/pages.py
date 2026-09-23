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

from encore.site import bands as bands_mod
from encore.site import i18n


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


def context(page: Page, *, locale: str, t: i18n.Translator, marts: dict[str, pd.DataFrame],
            bands: tuple[str, ...]) -> dict[str, Any]:
    """Page-specific template variables (grows as page content is added)."""
    return {"t": t, "locale": locale, "lang": locale, "page": page, "band": page.band,
            "bands": bands, "band_slug": bands_mod.slug(page.band) if page.band else None}
