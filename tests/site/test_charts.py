"""T5: charts are inline, themeable, accessible and deterministic; band colours are checked for contrast."""

import re

import pytest

from encore.site import bands, shape, theme
from encore.site.charts import Chart, Curve, Series, album_color, km_chart, line_chart, tour_median_bars
from encore.site.i18n import fmt_number
from tests.site.fixtures import BANDS, fake_marts


def nf(value: float, decimals: int) -> str:
    return fmt_number(value, decimals, "en")


@pytest.fixture(scope="module")
def marts():
    return fake_marts()


def _age_chart(marts, names=("Muse", "Oasis"), prefix="c1") -> Chart:
    colors = theme.band_colors()
    series = []
    for name in names:
        d = shape.age_by_year(marts["mart_repertoire_age"], name)
        series.append(Series(name, colors[name], d["show_year"].tolist(), d["avg_age"].tolist()))
    return line_chart(series, title="Repertoire age", desc="Average age by year", ylabel="years", nf=nf,
                      prefix=prefix, year_header="Year")


def _all_charts(marts) -> list[Chart]:
    colors = theme.band_colors()
    rot = shape.rotation_by_year(marts["mart_band_rotation_by_year"], "Muse")
    cells = shape.age_by_tour_cell(marts["mart_repertoire_age"], "Muse", min_shows=10)
    curves = [Curve("Album One (10)", album_color(0, "Album One"),
                    shape.km_curve(marts["mart_survival_curves"], "Muse", "Album One")),
              Curve("non-album (10)", album_color(2, "non-album"),
                    shape.km_curve(marts["mart_survival_curves"], "Muse", "non-album")),
              Curve("All", theme.LIGHT["ink"], shape.km_curve(marts["mart_survival_curves"], "Muse", "all"), True)]
    return [
        _age_chart(marts),
        line_chart([Series("Muse", colors["Muse"], rot["show_year"].tolist(), rot["rotation"].tolist(),
                           rot["thin"].tolist())], title="Rotation", desc="Rotation by year", ylabel="rotation",
                   nf=nf, prefix="c2", year_header="Year", ylim=(0, 1), decimals=2, compact=True),
        tour_median_bars(cells, color=colors["Muse"], title="Tours", desc="Median age by tour", xlabel="years",
                         mean_label="mean", nf=nf, prefix="c3", headers=["Tour", "Year", "Shows", "Median", "Mean"]),
        km_chart(curves, title="Survival", desc="Share still played", xlabel="shows", ylabel="share", median_label="median",
                 nf=nf, prefix="c4", first_header="Album", t_header="after {t}"),
    ]


def test_charts_are_inline_svg_with_text_alternative(marts) -> None:
    for chart in _all_charts(marts):
        assert chart.svg.startswith("<svg") and chart.svg.rstrip().endswith("</svg>")
        assert 'role="img"' in chart.svg and "<title" in chart.svg and "<desc" in chart.svg
        assert "<?xml" not in chart.svg and "<metadata" not in chart.svg and "<!DOCTYPE" not in chart.svg
        assert " width=" not in chart.svg.split(">", 1)[0] and " height=" not in chart.svg.split(">", 1)[0]
        assert chart.headers and chart.rows and all(len(r) == len(chart.headers) for r in chart.rows)


def test_no_fixed_colours_left_only_theme_variables(marts) -> None:
    for chart in _all_charts(marts):
        assert re.findall(r"#[0-9a-fA-F]{6}\b", chart.svg) == []
        assert "var(--" in chart.svg
        assert "font-family: var(--font-mono)" in chart.svg and "DejaVu" not in chart.svg


def test_band_colour_and_theme_tokens_are_used(marts) -> None:
    svg = _age_chart(marts).svg
    assert "var(--band-muse)" in svg and "var(--band-oasis)" in svg
    assert "var(--ink)" in svg or "var(--muted)" in svg


def test_charts_are_deterministic(marts) -> None:
    assert _age_chart(marts).svg == _age_chart(marts).svg


def test_ids_are_prefixed_so_charts_can_share_a_page(marts) -> None:
    a, b = _age_chart(marts, prefix="one"), _age_chart(marts, prefix="two")
    ids_a = set(re.findall(r'\bid="([^"]+)"', a.svg))
    ids_b = set(re.findall(r'\bid="([^"]+)"', b.svg))
    assert ids_a and ids_a.isdisjoint(ids_b)
    assert all(i.startswith("one-") for i in ids_a)
    for ref in re.findall(r"url\(#([^)]+)\)|href=\"#([^\"]+)\"", a.svg):
        assert any(r.startswith("one-") for r in ref if r)


def test_line_chart_table_marks_thin_years_and_gaps() -> None:
    s1 = Series("A", "#2a78d6", [2001, 2002], [0.5, 0.25], [False, True])
    s2 = Series("B", "#eb6834", [2002], [0.75])
    chart = line_chart([s1, s2], title="t", desc="d", ylabel="y", nf=nf, prefix="t", year_header="Year", decimals=2)
    assert chart.headers == ["Year", "A", "B"]
    assert chart.rows == [["2001", "0.50", "–"], ["2002", "0.25*", "0.75"]]


def test_km_table_gives_survival_at_checkpoints(marts) -> None:
    km = _all_charts(marts)[3]
    assert km.headers == ["Album", "after 25", "after 50", "after 100", "after 200", "after 400"]
    # Fixture curve: S(t=10)=0.85, S(20)=0.70, S(30)=0.55, S(40)=0.40, S(50)=0.25, so S(25) = 70%.
    assert km.rows[0][1] == "70%" and km.rows[0][2] == "25%" and km.rows[0][3] == "–"


def test_localised_words_appear_in_the_chart(marts) -> None:
    svg = km_chart(
        [Curve("x", "#2a78d6", shape.km_curve(marts["mart_survival_curves"], "Muse", "all"))], title="t", desc="d",
        xlabel="XLABEL", ylabel="YLABEL", median_label="MEDLABEL", nf=nf, prefix="p", first_header="a", t_header="{t}",
    ).svg
    assert "XLABEL" in svg and "YLABEL" in svg and "MEDLABEL" in svg


# Contrast of each band colour with the card surface of each theme. The 3:1 target for
# graphics holds except for the three pairs below, kept as approved colours and listed
# for a decision (docs/specs/spec-04-progress.md, T5).
PENDING_DECISION = {("Linkin Park", "light"), ("Muse", "light"), ("Avenged Sevenfold", "dark")}


@pytest.mark.parametrize("theme_name", ["light", "dark"])
def test_band_colour_contrast(theme_name: str) -> None:
    for name, colour in theme.band_colors().items():
        ratio = theme.contrast(colour, theme.SURFACES[theme_name])
        if (name, theme_name) in PENDING_DECISION:
            assert ratio < 3.0, f"{name} now passes on {theme_name}; remove it from PENDING_DECISION"
        else:
            assert ratio >= 3.0, f"{name} on {theme_name}: {ratio:.2f}"


def test_text_colours_are_readable_in_both_themes() -> None:
    assert theme.contrast(theme.LIGHT["muted"], theme.LIGHT["card"]) >= 4.5
    assert theme.contrast(theme.DARK["muted"], theme.DARK["card"]) >= 4.5
    assert theme.contrast(theme.LIGHT["ink"], theme.LIGHT["bg"]) >= 7
    assert theme.contrast(theme.DARK["ink"], theme.DARK["bg"]) >= 7


def test_tokens_css_covers_every_band_and_both_themes() -> None:
    css = theme.tokens_css()
    for name in BANDS:
        assert f"--band-{bands.slug(name)}:" in css
    assert ':root[data-theme="dark"]' in css and "--card: #1e1d19" in css
