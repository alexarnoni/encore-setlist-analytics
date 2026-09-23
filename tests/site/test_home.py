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


def test_hero_stats_and_the_three_layers_render(built_site: Path) -> None:
    text = text_of(built_site, "en", "").text
    # The fixture has no 2022/2023 Metallica data and no Morning Glory album, so the figures the findings quote
    # from real data are the stand-in "0"; the structure around them is what is checked.
    assert "years off Metallica's setlist in 2023, the year of 72 Seasons" in text
    assert "of the songs on (What's the Story) Morning Glory? were still being played 0 shows after their live debut" in text
    assert "500 shows after a song's live debut" in text  # the Oasis horizon figure is in the numbers
    pt = text_of(built_site, "pt", "").text
    assert "das músicas de (What's the Story) Morning Glory? ainda eram tocadas 0 shows depois da estreia ao vivo" in pt
    html = (built_site / "en" / "index.html").read_text(encoding="utf8")
    for n in (1, 2, 3):
        block = html[html.index(f'id="finding-{n}"'):]
        block = block[: block.index("</article>")]
        assert block.index("claim") < block.index("<p>") < block.index('class="caveats"'), n  # lead, numbers, caveats
        assert '<details class="caveats">' in block and "Caveats and limits" in block
    assert "On its latest tour Metallica played a substantially different set" in text


def test_every_chart_on_every_page_has_a_reading_line(built_site: Path) -> None:
    for page in built_site.rglob("index.html"):
        html = page.read_text(encoding="utf8")
        figures = html.count("<figure")
        assert html.count('class="read"') >= figures, page
    home = (built_site / "pt" / "index.html").read_text(encoding="utf8")
    assert home.count('class="read"') == 3 and "Como ler:" in home  # age line, rotation panels, survival curves


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
