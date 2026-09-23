"""T11: the content policy check fails on forbidden fields, precise dates and bad attribution."""

from datetime import date
from pathlib import Path

import pytest

from encore.site import build, policy
from tests.site.conftest import BUILT_ON, ORIGIN, findings_fill
from tests.site.fixtures import BANDS, fake_marts

STAMP = ('<div data-build-stamp><time datetime="2026-09-23">2026-09-23</time> '
         '<time datetime="2026-09-24">2026-09-24</time></div>')
CREDIT = ('<a href="https://www.setlist.fm/">setlist.fm</a> <a href="https://musicbrainz.org/">MusicBrainz</a> (CC0).')


def page(body: str = "<p>Muse played 2,059 performances between 1994 and 2004.</p>", stamp: str = STAMP,
         credit: str = CREDIT) -> str:
    return f"<html><body>{stamp}<main>{body}</main><footer>{credit}</footer></body></html>"


def rules(html: str) -> list[str]:
    return [v.rule for v in policy.check_html(html, "p.html")]


def test_a_clean_page_passes() -> None:
    assert policy.check_html(page(), "p.html") == []


@pytest.mark.parametrize("field", ["setlist_id", "show_date", "song_name_raw", "show_key", "show_id", "show_index",
                                   "setlist_url", "SETLIST_ID"])
def test_forbidden_field_names_fail_anywhere(field: str) -> None:
    assert "forbidden field name" in rules(page(f"<p>column {field} here</p>"))
    assert "forbidden field name" in rules(page("<p>ok</p>", credit=CREDIT + f"<!-- {field} -->"))


def test_venue_is_fine_in_prose_but_not_as_a_field() -> None:
    assert rules(page("<p>The site never shows a venue or a show date.</p>")) == []
    assert "forbidden field name" in rules(page('<div class="venue">x</div>'))
    assert "forbidden field name" in rules(page("<table><tr><th>Venue</th></tr></table>"))
    assert "forbidden field name" in rules(page('<td data-venue="x">x</td>'))


@pytest.mark.parametrize("text", [
    "on 2019-05-01", "on 01/05/2019", "on 1.5.2019", "on 1 May 2019", "on 1st of May", "1 de maio de 2019",
    "May 2019", "March 5", "em março de 2020", "on 2019-05-01T20:00:00",
])
def test_dates_more_precise_than_a_year_fail(text: str) -> None:
    assert "date more precise than a year" in rules(page(f"<p>{text}</p>"))


def test_a_date_in_an_attribute_fails_too() -> None:
    assert "date more precise than a year" in rules(page('<p title="2019-05-01">x</p>'))
    assert "date more precise than a year" in rules(page('<a href="/x/2019-05-01/">x</a>'))


@pytest.mark.parametrize("text", ["1994–2004", "since 2015", "N = 25", "92.9%", "1,235 shows", "0.25% of performances",
                                  "from 32.3 to 25.4", "the figures may be wrong"])
def test_years_numbers_and_ordinary_words_pass(text: str) -> None:
    assert rules(page(f"<p>{text}</p>")) == []


def test_svg_geometry_is_not_read_as_dates() -> None:
    svg = '<svg><path d="M 10.5.3 L 1.2.2026 4.5.6" transform="translate(1.5.2020)" style="fill: red"></path></svg>'
    assert rules(page(svg)) == []


def test_the_stamp_is_the_only_place_for_full_dates() -> None:
    assert rules(page()) == []
    assert "date more precise than a year" in rules(page("<p>built 2026-09-24</p>"))
    nested = STAMP.replace("</div>", "<div><span>x</span></div></div>")  # a nested element does not end the exemption early
    assert rules(page(stamp=nested)) == []
    assert "date more precise than a year" in rules(page("<p>2026-09-24</p>", stamp=nested))


def test_the_stamp_must_exist_and_hold_two_dates() -> None:
    assert "build stamp" in rules(page(stamp=""))
    assert "build stamp" in rules(page(stamp="<div data-build-stamp><time>2026-09-23</time></div>"))


def test_setlistfm_links_must_point_at_the_root() -> None:
    deep = CREDIT + '<a href="https://www.setlist.fm/setlist/muse/2019/x-1234.html">x</a>'
    assert rules(page(credit=deep)) == ["setlist.fm link"]
    assert rules(page(credit=CREDIT + '<a href="https://www.setlist.fm/">ok</a>')) == []
    assert "setlist.fm link" in rules(page(credit=CREDIT + '<a href="https://setlist.fm/search?query=muse">x</a>'))


def test_attribution_is_required_and_followable() -> None:
    assert "attribution" in rules(page(credit='<a href="https://musicbrainz.org/">MusicBrainz</a> CC0'))
    nofollow = CREDIT.replace('<a href="https://www.setlist.fm/">', '<a rel="nofollow" href="https://www.setlist.fm/">')
    assert "attribution" in rules(page(credit=nofollow))
    assert "attribution" in rules(page(credit='<a href="https://www.setlist.fm/">setlist.fm</a>'))  # no MusicBrainz / CC0


def test_the_redirect_page_only_gets_the_content_rules() -> None:
    html = ('<html><head><meta http-equiv="refresh" content="0; url=/pt/"></head>'
            '<body><a href="/pt/">Português</a></body></html>')
    assert policy.check_html(html, "index.html", is_page=False) == []
    assert "forbidden field name" in [v.rule for v in policy.check_html(html + " show_id", "index.html", is_page=False)]


def test_the_generated_site_passes(built_site: Path) -> None:
    assert policy.check_site(built_site) == []
    policy.enforce(built_site)


def test_the_build_fails_and_leaves_no_pages_when_marts_carry_a_forbidden_field(tmp_path: Path) -> None:
    marts = fake_marts()
    s = marts["mart_survival_summary"]
    marts["mart_survival_summary"] = s.assign(album=s["album"].replace({"Album One": "Live show_id 42"}))
    out = tmp_path / "site"
    with pytest.raises(policy.PolicyError, match="show_id"):
        build.build_site(marts, out, built_on=BUILT_ON, origin=ORIGIN, bands=tuple(BANDS), fill_missing=findings_fill)
    assert out.exists() and list(out.iterdir()) == []


def test_the_build_fails_when_a_precise_date_reaches_a_page(tmp_path: Path) -> None:
    marts = fake_marts()
    s = marts["mart_survival_summary"]
    marts["mart_survival_summary"] = s.assign(album=s["album"].replace({"Album Two": "Live 2019-05-01"}))
    with pytest.raises(policy.PolicyError, match="date more precise than a year"):
        build.build_site(marts, tmp_path / "site", built_on=date(2026, 9, 24), origin=ORIGIN, bands=tuple(BANDS),
                         fill_missing=findings_fill)
