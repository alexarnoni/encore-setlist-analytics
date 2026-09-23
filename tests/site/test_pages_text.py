"""T7: methodology and about pages: content, numbers from the marts, and strict placeholders."""

import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

from encore.site import bands, build, i18n
from tests.site.conftest import BUILT_ON, ORIGIN, findings_fill, parse
from tests.site.fixtures import BANDS, fake_marts


class Text(HTMLParser):
    """Visible text of a page plus the cells of its tables."""

    def __init__(self, html: str) -> None:
        super().__init__(convert_charrefs=True)
        self.chunks: list[str] = []
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: str | None = None
        self._skip = 0
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        if tag == "tr":
            self._row = []
        if tag in ("td", "th"):
            self._cell = ""

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip -= 1
        if tag in ("td", "th") and self._row is not None and self._cell is not None:
            self._row.append(self._cell.strip())
            self._cell = None
        if tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._skip:
            return
        self.chunks.append(data)
        if self._cell is not None:
            self._cell += data

    @property
    def text(self) -> str:
        return " ".join("".join(self.chunks).split())


def text_of(site: Path, locale_prefix: str, path: str) -> Text:
    return Text((site / locale_prefix / path / "index.html").read_text(encoding="utf8"))


def test_methodology_sections_exist_in_both_locales(built_site: Path) -> None:
    for prefix in ("pt", "en"):
        page = parse(built_site / prefix / "methodology" / "index.html")
        assert {"scope", "kpi", "survival", "sensitivity", "policy", "limitations", "match"} <= page.ids


def test_sensitivity_table_matches_the_marts(built_site: Path) -> None:
    rows = text_of(built_site, "en", "methodology/").rows
    sensitivity = [r for r in rows if r and r[0] in BANDS and r[1].replace(",", "").isdigit() and len(r) == 4]
    by_band = {r[0]: r[1:] for r in sensitivity}
    assert by_band["Linkin Park"] == ["127", "152", "202"]  # fixture: 100 + N + band index 2
    assert by_band["Muse"] == ["129", "154", "204"]
    assert list(by_band) == BANDS


def test_match_table_weights_by_performances(built_site: Path) -> None:
    rows = text_of(built_site, "en", "methodology/").rows
    muse = next(r for r in rows if r[0] == "Muse" and len(r) == 5)
    assert muse[1] == "2,059" and muse[2] == "92.9%" and muse[3] == "82.9%"  # album: (5*340 + 0.1*9 + 0.1*50) / 2,059
    assert muse[4] == "1994–2004"
    portuguese = next(r for r in text_of(built_site, "pt", "methodology/").rows if r[0] == "Muse" and len(r) == 5)
    assert portuguese[1] == "2.059" and portuguese[2] == "92,9%"


def test_limitations_are_filled_from_the_marts(built_site: Path) -> None:
    en = text_of(built_site, "en", "methodology/").text
    assert "0 of 9 performances matched in 1994 and 12 of 50 in 1995 (24.0%)" in en
    assert "2.87% of Muse's performances" in en
    assert "about 33 show pairs for Twenty One Pilots (its busiest year has 33)" in en  # 30 + band index 3
    pt = text_of(built_site, "pt", "methodology/").text
    assert "0 de 9 execuções reconhecidas em 1994" in pt and "2,87% das execuções do Muse" in pt


def test_no_unrendered_template_syntax_on_any_page(built_site: Path) -> None:
    for page in built_site.rglob("index.html"):
        html = page.read_text(encoding="utf8")
        assert "{{" not in html and "{%" not in html, page


def test_methodology_and_about_carry_the_policy_statements(built_site: Path) -> None:
    en = text_of(built_site, "en", "methodology/").text
    assert "deleted at the end of every run" in en and "CC0" in en and "non-album" in en
    about = parse(built_site / "en" / "about" / "index.html")
    hrefs = {l["href"] for l in about.links}
    assert "https://github.com/alexarnoni/encore-setlist-analytics" in hrefs
    assert {"stack", "purpose", "source"} <= about.ids


def test_a_limitation_without_data_fails_the_build(tmp_path: Path) -> None:
    """If the marts stop having Muse's weak years, the text that quotes them must not ship stale."""
    marts = fake_marts()
    marts["mart_match_quality"] = marts["mart_match_quality"].query("show_year >= 2000")
    with pytest.raises(i18n.LocaleError, match="muse_1994"):
        build.build_site(marts, tmp_path / "out", built_on=BUILT_ON, origin=ORIGIN, bands=tuple(BANDS),
                         fill_missing=findings_fill)
