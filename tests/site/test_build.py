"""T6: the build writes the same page set in both locales, with the layout the spec requires."""

from pathlib import Path

import pytest

from encore.site import bands, build, i18n
from tests.site.conftest import BUILT_ON, ORIGIN, parse
from tests.site.fixtures import BANDS, fake_marts

FIXED = ["", "comparison/", "methodology/", "about/"]
EXPECTED = FIXED + [f"bands/{bands.slug(b)}/" for b in BANDS]
PREFIX = {"pt-BR": "pt", "en": "en"}


def pages_of(site: Path, prefix: str) -> set[str]:
    root = site / prefix
    return {p.parent.relative_to(root).as_posix().replace(".", "") + "/" if p.parent != root else ""
            for p in root.rglob("index.html")}


def test_output_dir_default_and_override(monkeypatch) -> None:
    monkeypatch.delenv("SITE_OUTPUT_DIR", raising=False)
    assert build.output_dir() == Path("site")
    monkeypatch.setenv("SITE_OUTPUT_DIR", "out")
    assert build.output_dir() == Path("out")


def test_every_page_exists_in_both_locales(built_site: Path) -> None:
    for prefix in PREFIX.values():
        assert pages_of(built_site, prefix) == set(EXPECTED)
    assert len(EXPECTED) == 4 + 7


def test_root_redirects_to_portuguese(built_site: Path) -> None:
    html = (built_site / "index.html").read_text(encoding="utf8")
    page = parse(built_site / "index.html")
    assert 'http-equiv="refresh" content="0; url=/pt/"' in html
    assert page.lang == "pt-BR"
    assert {l["href"] for l in page.links} == {"/pt/", "/en/"}


@pytest.mark.parametrize("locale", ["pt-BR", "en"])
def test_html_lang_and_hreflang_pairs(built_site: Path, locale: str) -> None:
    for path in EXPECTED:
        page = parse(built_site / PREFIX[locale] / path / "index.html")
        assert page.lang == locale
        alternates = {l["hreflang"]: l["href"] for l in page.head_links if l.get("rel") == "alternate"}
        assert alternates == {
            "pt-BR": f"{ORIGIN}/pt/{path}", "en": f"{ORIGIN}/en/{path}", "x-default": f"{ORIGIN}/pt/{path}"}
        canonical = [l["href"] for l in page.head_links if l.get("rel") == "canonical"]
        assert canonical == [f"{ORIGIN}/{PREFIX[locale]}/{path}"]


def test_language_switcher_preserves_the_page(built_site: Path) -> None:
    for path in EXPECTED:
        page = parse(built_site / "pt" / path / "index.html")
        switch = {l["hreflang"]: l["href"] for l in page.links if "hreflang" in l}
        assert switch == {"pt-BR": f"/pt/{path}", "en": f"/en/{path}"}
        current = [l["hreflang"] for l in page.links if l.get("aria-current") == "true"]
        assert current == ["pt-BR"]


def test_every_page_has_followable_setlistfm_and_musicbrainz_credit(built_site: Path) -> None:
    for prefix in PREFIX.values():
        for path in EXPECTED:
            html = (built_site / prefix / path / "index.html").read_text(encoding="utf8")
            page = parse(built_site / prefix / path / "index.html")
            setlistfm = [l for l in page.links if "setlist.fm" in l.get("href", "")]
            assert setlistfm and all("nofollow" not in l.get("rel", "") for l in setlistfm)
            assert "nofollow" not in html
            assert any("musicbrainz.org" in l.get("href", "") for l in page.links)
            assert "CC0" in html


def test_theme_toggle_light_default_and_localstorage_key(built_site: Path) -> None:
    for prefix in PREFIX.values():
        page = parse(built_site / prefix / "index.html")
        script = page.scripts[0]
        assert "encore-theme" in script and "prefers-color-scheme" not in script
        assert "if (theme !== 'dark') { theme = 'light'; }" in script  # stored choice, else light
        assert script.count("try {") == 2  # every localStorage access is guarded
        assert any(tag == "button" and "theme-toggle" in a.get("class", "") for tag, a in page.tags)
        # The script runs in <head> before the stylesheet, so the theme is set before first paint.
        html = (built_site / prefix / "index.html").read_text(encoding="utf8")
        assert html.index("encore-theme") < html.index("/assets/site.css")


def test_status_line_carries_both_dates_in_one_marked_element(built_site: Path) -> None:
    html = (built_site / "en" / "index.html").read_text(encoding="utf8")
    start = html.index("data-build-stamp")
    element = html[start: html.index("</div>\n</div>", start)]
    assert "2026-09-23" in element and BUILT_ON.isoformat() in element
    assert html.count("2026-09-23") == html.count("2026-09-23", start, start + len(element)) == 2  # time + datetime


def test_stylesheet_has_generated_tokens_and_both_themes(built_site: Path) -> None:
    css = (built_site / "assets" / "site.css").read_text(encoding="utf8")
    assert "--band-muse:" in css and ':root[data-theme="dark"]' in css and ".site-header" in css


def test_missing_translation_key_fails_the_build(tmp_path: Path) -> None:
    (tmp_path / "loc").mkdir()
    real = i18n.load_locales()
    import yaml
    for locale in i18n.LOCALES:
        strings = {k: v for k, v in real[locale].items() if k != "footer.source"}
        nested: dict = {}
        for key, value in strings.items():
            node = nested
            *parents, leaf = key.split(".")
            for p in parents:
                node = node.setdefault(p, {})
            node[leaf] = value
        (tmp_path / "loc" / f"{locale}.yml").write_text(yaml.safe_dump(nested, allow_unicode=True), encoding="utf8")
    with pytest.raises(i18n.LocaleError, match="footer.source"):
        build.build_site(fake_marts(), tmp_path / "out", built_on=BUILT_ON, origin=ORIGIN,
                         locales_dir=tmp_path / "loc", bands=tuple(BANDS))
