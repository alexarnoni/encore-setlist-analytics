"""T9: one page per band with findings, four charts (or their fallbacks), the album table and links."""

from pathlib import Path

import pytest

from encore.site import bands, sections
from encore.site.charts import album_color, album_linestyle
from tests.site.conftest import parse
from tests.site.fixtures import BANDS
from tests.site.test_pages_text import text_of


@pytest.mark.parametrize("index,band", list(enumerate(BANDS)))
def test_every_band_page_has_its_sections_and_charts(built_site: Path, index: int, band: str) -> None:
    for prefix in ("pt", "en"):
        path = built_site / prefix / "bands" / bands.slug(band) / "index.html"
        page = parse(path)
        assert {"findings", "age", "rotation", "survival", "albums", "others"} <= page.ids
        html = path.read_text(encoding="utf8")
        # Fixture tour cells have 10 + index shows; the tour chart needs 15, so it is skipped below index 5.
        assert html.count("<svg") == (4 if index >= 5 else 3)
        assert f"var(--band-{bands.slug(band)})" in html


def test_band_header_chips_come_from_the_marts(built_site: Path) -> None:
    text = text_of(built_site, "en", "bands/muse/").text
    assert "1994–2004" in text and "70 shows" in text and "92.9% matched to the catalog" in text
    assert "median survival: 154 shows" in text
    pt = text_of(built_site, "pt", "bands/muse/").text
    assert "92,9% reconhecidas no catálogo" in pt and "sobrevivência mediana: 154 shows" in pt


def test_album_table_matches_the_marts(built_site: Path) -> None:
    rows = text_of(built_site, "en", "bands/oasis/").rows
    table = [r for r in rows if r and r[0] in ("All songs", "Album One", "Album Two", "non-album")]
    assert table == [
        ["All songs", "30", "15", "15", "151"], ["Album One", "10", "5", "5", "151"],
        ["Album Two", "10", "5", "5", "151"], ["non-album", "10", "5", "5", "not reached"]]


def test_survival_alternative_gives_share_at_checkpoints(built_site: Path) -> None:
    rows = text_of(built_site, "en", "bands/oasis/").rows
    header = next(r for r in rows if r and r[0] == "Album" and len(r) == 6)
    assert header[1:] == ["after 25 shows", "after 50 shows", "after 100 shows", "after 200 shows", "after 400 shows"]
    all_songs = next(r for r in rows if r and r[0].startswith("All songs (") and len(r) == 6)
    assert all_songs[1:] == ["70%", "25%", "–", "–", "–"]  # fixture curve, see test_charts


def test_tour_chart_and_thin_year_note_are_present(built_site: Path) -> None:
    text = text_of(built_site, "en", "bands/metallica/")
    assert "Cells with fewer than 15 shows are left out." in text.text
    assert "Hollow markers: years with fewer than 5 show pairs" in text.text
    assert "Tour A 2000" in text.text  # Metallica's fixture cells have exactly 15 shows: at the floor, kept
    fewer = text_of(built_site, "en", "bands/muse/").text
    assert "Median age by tour" not in fewer  # Muse's cells have 14: no cell qualifies, the block is omitted


def test_other_bands_links_exclude_the_page_itself(built_site: Path) -> None:
    page = parse(built_site / "en" / "bands" / "muse" / "index.html")
    others = [l["href"] for l in page.links if l["href"].startswith("/en/bands/") and "hreflang" not in l]
    assert sorted(others) == sorted(f"/en/bands/{bands.slug(b)}/" for b in BANDS if b != "Muse")


def test_confidence_bands_only_for_few_curves() -> None:
    assert sections.show_ci(6) and not sections.show_ci(7)


def test_more_albums_than_colours_get_a_different_line_style() -> None:
    assert album_linestyle(0) == "-" and album_linestyle(6) == "-"
    assert album_linestyle(7) != "-"
    assert album_color(7, "x") == album_color(0, "y") and album_color(3, "non-album") != album_color(3, "x")
