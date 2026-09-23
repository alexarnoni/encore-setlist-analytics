"""T13: no broken internal link, anchor or alternate in the generated site."""

import shutil
from pathlib import Path

import pytest

from encore.site import build, linkcheck
from tests.site.conftest import BUILT_ON, ORIGIN, findings_fill
from tests.site.fixtures import BANDS, fake_marts


def rules(out: Path) -> list[str]:
    return [v.rule for v in linkcheck.check_links(out, ORIGIN)]


@pytest.fixture()
def site(tmp_path: Path, built_site: Path) -> Path:
    """A private copy of the built site that a test may break."""
    copy = tmp_path / "site"
    shutil.copytree(built_site, copy)
    return copy


def test_the_generated_site_has_no_broken_links(built_site: Path) -> None:
    assert linkcheck.check_links(built_site, ORIGIN) == []
    linkcheck.enforce(built_site, ORIGIN)


def test_the_check_really_visits_links(built_site: Path) -> None:
    """Guard against a check that passes because it looked at nothing."""
    pages = list(built_site.rglob("*.html"))
    assert len(pages) == 2 * (4 + len(BANDS)) + 1
    assert any("/en/bands/muse/" in p.read_text(encoding="utf8") for p in pages)


def test_a_broken_internal_link_fails(site: Path) -> None:
    page = site / "en" / "about" / "index.html"
    page.write_text(page.read_text(encoding="utf8").replace("</main>", '<a href="/en/nope/">x</a></main>'), encoding="utf8")
    assert rules(site) == ["broken link"]


def test_a_missing_anchor_fails(site: Path) -> None:
    page = site / "pt" / "about" / "index.html"
    page.write_text(page.read_text(encoding="utf8").replace("</main>", '<a href="/pt/methodology/#nowhere">x</a></main>'),
                    encoding="utf8")
    assert rules(site) == ["broken anchor"]
    ok = page.read_text(encoding="utf8").replace("#nowhere", "#sensitivity")
    page.write_text(ok, encoding="utf8")
    assert rules(site) == []


def test_a_missing_stylesheet_or_alternate_fails(site: Path) -> None:
    (site / "assets" / "site.css").unlink()
    assert set(rules(site)) == {"broken link"}
    css = site / "assets" / "site.css"
    css.write_text("", encoding="utf8")
    (site / "en" / "about" / "index.html").unlink()  # the hreflang alternates and the switcher now point nowhere
    broken = linkcheck.check_links(site, ORIGIN)
    assert broken and all(v.rule == "broken link" for v in broken)
    assert any("/en/about/" in v.detail for v in broken)


def test_relative_and_fragment_only_links_resolve_against_the_page(site: Path) -> None:
    page = site / "en" / "bands" / "muse" / "index.html"
    html = page.read_text(encoding="utf8")
    page.write_text(html.replace("</main>", '<a href="#age">a</a><a href="../oasis/">b</a><a href="../ghost/">c</a></main>'),
                    encoding="utf8")
    found = linkcheck.check_links(site, ORIGIN)
    assert [v.rule for v in found] == ["broken link"] and "../ghost/" in found[0].detail


def test_external_and_mail_links_are_not_fetched(site: Path) -> None:
    page = site / "en" / "about" / "index.html"
    page.write_text(page.read_text(encoding="utf8").replace(
        "</main>", '<a href="https://example.org/x">e</a><a href="mailto:a@b.c">m</a></main>'), encoding="utf8")
    assert rules(site) == []


def test_the_root_redirect_target_exists(built_site: Path) -> None:
    html = (built_site / "index.html").read_text(encoding="utf8")
    assert 'url=/pt/' in html and (built_site / "pt" / "index.html").is_file()


def test_the_build_fails_and_leaves_no_pages_on_a_broken_link(tmp_path: Path, monkeypatch) -> None:
    real = build.pages.href
    # Point the nav at a page that is never written.
    monkeypatch.setattr(build.pages, "href", lambda locale, path: real(locale, "gone/" if path == "about/" else path))
    out = tmp_path / "site"
    with pytest.raises(linkcheck.LinkError, match="broken link"):
        build.build_site(fake_marts(), out, built_on=BUILT_ON, origin=ORIGIN, bands=tuple(BANDS),
                         fill_missing=findings_fill)
    assert out.exists() and list(out.iterdir()) == []
