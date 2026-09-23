"""Shared fixtures: the fake marts and a site built from them once per test session."""

from datetime import date
from html.parser import HTMLParser
from pathlib import Path

import pytest

from encore.site import build, values
from tests.site.fixtures import BANDS, fake_marts

BUILT_ON = date(2026, 9, 24)
ORIGIN = "https://example.test"


def findings_fill(name: str) -> str | None:
    """Stand-in for the real-data figures the findings quote (see `values.FINDINGS_KEY`); nothing else is filled."""
    return "0" if values.FINDINGS_KEY.match(name) else None


@pytest.fixture(scope="session")
def built_site(tmp_path_factory) -> Path:
    """Build the whole site from the fake marts into a temp dir."""
    out = tmp_path_factory.mktemp("site")
    build.build_site(fake_marts(), out, built_on=BUILT_ON, origin=ORIGIN, bands=tuple(BANDS), fill_missing=findings_fill)
    return out


class Page(HTMLParser):
    """Collects what the tests look at: html lang, links, ids, head links and inline scripts."""

    def __init__(self, html: str) -> None:
        super().__init__(convert_charrefs=True)
        self.lang: str | None = None
        self.links: list[dict[str, str]] = []  # <a>
        self.head_links: list[dict[str, str]] = []  # <link>
        self.ids: set[str] = set()
        self.scripts: list[str] = []
        self.tags: list[tuple[str, dict[str, str]]] = []
        self._in_script = False
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        self.tags.append((tag, a))
        if tag == "html":
            self.lang = a.get("lang")
        if tag == "a":
            self.links.append(a)
        if tag == "link":
            self.head_links.append(a)
        if "id" in a:
            self.ids.add(a["id"])
        if tag == "script":
            self._in_script = True
            self.scripts.append("")

    def handle_endtag(self, tag):
        if tag == "script":
            self._in_script = False

    def handle_data(self, data):
        if self._in_script:
            self.scripts[-1] += data


def parse(path: Path) -> Page:
    return Page(path.read_text(encoding="utf8"))
