"""T8: the comparison page shows every band on shared axes, plus the median survival table."""

from pathlib import Path

from tests.site.conftest import parse
from tests.site.fixtures import BANDS
from tests.site.test_pages_text import text_of


def test_comparison_has_two_charts_with_seven_bands_each(built_site: Path) -> None:
    for prefix in ("pt", "en"):
        html = (built_site / prefix / "comparison" / "index.html").read_text(encoding="utf8")
        assert html.count("<svg") == 2
        for band in ("muse", "oasis", "metallica", "twenty-one-pilots"):
            assert html.count(f"var(--band-{band})") >= 2  # in both charts (line and marker)
        page = parse(built_site / prefix / "comparison" / "index.html")
        assert {"age", "rotation", "survival"} <= page.ids


def test_every_chart_has_a_text_alternative_with_all_bands(built_site: Path) -> None:
    text = text_of(built_site, "en", "comparison/")
    header_rows = [r for r in text.rows if r and r[0] == "Year"]
    assert len(header_rows) == 2 and all(r[1:] == BANDS for r in header_rows)
    assert "Hollow markers: years with fewer than 5 show pairs" in text.text


def test_median_survival_table_is_in_band_order(built_site: Path) -> None:
    rows = text_of(built_site, "en", "comparison/").rows
    table = [r for r in rows if len(r) == 5 and r[0] in BANDS]
    assert [r[0] for r in table] == BANDS
    assert table[0][1:] == ["30", "15", "15", "150"]  # fixture: songs, abandoned, censored, median at N = 50
    assert table[5][4] == "155"  # Metallica is band 5


def test_portuguese_page_uses_portuguese_words_and_numbers(built_site: Path) -> None:
    text = text_of(built_site, "pt", "comparison/")
    assert "Quanto tempo as músicas duram: sobrevivência mediana por banda" in text.text
    assert any(r and r[0] == "Ano" for r in text.rows)
