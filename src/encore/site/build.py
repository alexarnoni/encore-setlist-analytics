"""Entry point: `python -m encore.site.build` builds the static site into `site/`.

The generator reads only the `analytics` schema and never contacts setlist.fm
(docs/specs/spec-04-site.md, working rules). Output: `site/index.html` (a redirect
to `/pt/`), then `site/pt/...` and `site/en/...`, one page set per locale, plus
`site/assets/`. Deploy is a separate, manual step (see README).
"""

from __future__ import annotations

import logging
import os
import shutil
from datetime import date
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from encore.site import bands as bands_mod
from encore.site import i18n, marts as marts_mod, pages, shape, theme, values

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT_DIR = "site"
DEFAULT_SITE_URL = "https://encore.alexarnoni.com"
REPO_URL = "https://github.com/alexarnoni/encore-setlist-analytics"
SETLISTFM_URL = "https://www.setlist.fm/"
MUSICBRAINZ_URL = "https://musicbrainz.org/"

PACKAGE_DIR = Path(__file__).parent
TEMPLATES_DIR = PACKAGE_DIR / "templates"
ASSETS_DIR = PACKAGE_DIR / "assets"


def output_dir() -> Path:
    """Return the build output directory (SITE_OUTPUT_DIR, default `site/`)."""
    return Path(os.environ.get("SITE_OUTPUT_DIR", DEFAULT_OUTPUT_DIR))


def site_url() -> str:
    """Public origin used in canonical and hreflang links (SITE_URL, default the production domain)."""
    return os.environ.get("SITE_URL", DEFAULT_SITE_URL).rstrip("/")


def _environment() -> Environment:
    return Environment(loader=FileSystemLoader(TEMPLATES_DIR), autoescape=True, undefined=StrictUndefined,
                       trim_blocks=True, lstrip_blocks=True)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf8", newline="\n")


def _copy_assets(out: Path) -> None:
    """Write `assets/site.css` (generated tokens + static styles) and copy self-hosted fonts."""
    css = theme.tokens_css() + "\n" + (ASSETS_DIR / "site.css").read_text(encoding="utf8")
    fonts = ASSETS_DIR / "fonts"
    if fonts.is_dir() and any(fonts.glob("*.woff2")):
        shutil.copytree(fonts, out / "assets" / "fonts", dirs_exist_ok=True)
        css = (ASSETS_DIR / "fonts.css").read_text(encoding="utf8") + "\n" + css
    _write(out / "assets" / "site.css", css)


def build_site(
    marts: dict[str, pd.DataFrame], out: Path, *, built_on: date, origin: str | None = None,
    locales_dir: Path = i18n.LOCALES_DIR, bands: tuple[str, ...] | None = None,
) -> list[Path]:
    """Render every page of every locale into `out` and return the written files.

    `out` is emptied first so a removed page never lingers. Raises `i18n.LocaleError`
    on a missing translation key or an unfilled placeholder.
    """
    origin = (origin or site_url()).rstrip("/")
    bands = bands or bands_mod.band_names()
    strings = i18n.load_locales(locales_dir)
    env = _environment()
    as_of = marts_mod.data_as_of(marts)
    shows_total = int(shape.shows_by_band(marts["mart_repertoire_age"]).sum())
    page_list = pages.page_list(bands)

    if out.exists():
        shutil.rmtree(out)
    written: list[Path] = []
    for locale in i18n.LOCALES:
        t = i18n.Translator(locale, strings[locale], values.placeholder_values(marts, bands, locale))
        for page in page_list:
            ctx = pages.context(page, locale=locale, t=t, marts=marts, bands=bands)
            ctx.update(
                origin=origin, as_of=as_of.isoformat(), built_on=built_on.isoformat(), shows_total=shows_total,
                bands_total=len(bands), repo_url=REPO_URL, setlistfm_url=SETLISTFM_URL,
                musicbrainz_url=MUSICBRAINZ_URL, layout=pages.layout(page, locale, page_list, t, origin),
            )
            html = env.get_template(page.template).render(**ctx)
            target = out / i18n.URL_PREFIX[locale] / page.path / "index.html"
            _write(target, html)
            written.append(target)

    t_default = i18n.Translator(i18n.DEFAULT_LOCALE, strings[i18n.DEFAULT_LOCALE])
    root = env.get_template("redirect.html").render(
        t=t_default, lang=i18n.DEFAULT_LOCALE, target=pages.href(i18n.DEFAULT_LOCALE, ""),
        canonical=origin + pages.href(i18n.DEFAULT_LOCALE, ""),
        alternates=[(loc, origin + pages.href(loc, "")) for loc in i18n.LOCALES],
        languages=[(loc, pages.href(loc, ""), strings[loc][f"lang.{loc}_name"]) for loc in i18n.LOCALES])
    _write(out / "index.html", root)
    written.append(out / "index.html")
    _copy_assets(out)
    logger.info("Built %d pages (%d locales) into %s", len(written), len(i18n.LOCALES), out)
    return written


def main() -> int:
    """Read the marts, build the site, run the content and link checks; return the exit code."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    load_dotenv()
    marts = marts_mod.load_all()
    out = output_dir()
    build_site(marts, out, built_on=date.today())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
