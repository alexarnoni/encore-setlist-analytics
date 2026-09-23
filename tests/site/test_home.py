"""T10: the home page: three findings (two hero stats, one set of small multiples) and the band index."""

from pathlib import Path

from encore.site import bands
from tests.site.conftest import parse
from tests.site.fixtures import BANDS
from tests.site.test_pages_text import text_of


def test_home_has_three_findings_and_the_band_index(built_site: Path) -> None:
    for prefix in ("pt", "en"):
        page = parse(built_site / prefix / "index.html")
        assert {"finding-1", "finding-2", "finding-3", "bands", "findings"} <= page.ids


def test_hero_stats_come_from_the_marts(built_site: Path) -> None:
    text = text_of(built_site, "en", "").text
    # The fixture has no 2022/2023 Metallica data and its curves stop at 50 shows, so the figures the
    # findings quote from real data are the stand-in "0"; the structure around them is what is checked.
    assert "of Oasis's eligible songs are still in the setlist 500 shows after their live debut" in text
    assert "years off Metallica's average repertoire age in 2023" in text
    pt = text_of(built_site, "pt", "").text
    assert "das músicas elegíveis do Oasis ainda estão no setlist 500 shows após a estreia ao vivo" in pt


def test_finding_two_uses_seven_small_multiples_not_a_hero_stat(built_site: Path) -> None:
    html = (built_site / "en" / "index.html").read_text(encoding="utf8")
    start, end = html.index('id="finding-2"'), html.index('id="finding-3"')
    block = html[start:end]
    assert block.count("<svg") == 7 and "multiples" in block and "hero-stat" not in block
    for band in BANDS:
        assert f'href="/en/bands/{bands.slug(band)}/"' in block
    assert "hero-stat" in html[html.index('id="finding-1"'):start]
    assert "hero-stat" in html[end:]


def test_finding_two_has_one_combined_text_alternative(built_site: Path) -> None:
    rows = text_of(built_site, "en", "").rows
    header = [r for r in rows if r and r[0] == "Year" and len(r) == 8]
    assert len(header) == 1 and header[0][1:] == BANDS


def test_band_index_lists_every_band_with_its_numbers(built_site: Path) -> None:
    rows = [r for r in text_of(built_site, "en", "").rows if len(r) == 5 and r[0] in BANDS]
    assert [r[0] for r in rows] == BANDS
    muse = next(r for r in rows if r[0] == "Muse")
    assert muse[1:] == ["1994–2004", "70", "92.9%", "154"]


def test_home_links_to_every_band_page(built_site: Path) -> None:
    page = parse(built_site / "en" / "index.html")
    hrefs = {l["href"] for l in page.links}
    assert {f"/en/bands/{bands.slug(b)}/" for b in BANDS} <= hrefs
