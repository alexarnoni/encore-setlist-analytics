"""T12: the hand-written findings only quote figures the build can supply, and their claims hold on real data."""

import os
import re
from pathlib import Path

import pytest

from encore.site import bands, build, i18n, marts as marts_mod, shape, values
from tests.site.fixtures import BANDS, fake_marts

# Placeholders a template fills at call time (the caller passes them), not from the marts.
CALL_TIME = {"min_pairs", "min_songs", "min_tour_shows", "n_window", "n", "band", "first", "last", "pct",
             "setlistfm_url", "musicbrainz_url", "repo_url", "author_url"}


def placeholders(strings: dict[str, str]) -> set[str]:
    return {name for text in strings.values() for name in re.findall(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}", text)}


def test_every_placeholder_in_the_text_is_a_known_kind_of_figure() -> None:
    """A typo such as `metalica_median` fails here, without needing the real data."""
    available = set(values.placeholder_values(fake_marts(), tuple(BANDS), "en"))
    for locale, strings in i18n.load_locales().items():
        unknown = {p for p in placeholders(strings)
                   if p not in available and p not in CALL_TIME and not values.FINDINGS_KEY.match(p)}
        assert not unknown, f"{locale}: {sorted(unknown)}"


def test_both_locales_quote_exactly_the_same_figures() -> None:
    loaded = i18n.load_locales()
    assert placeholders(loaded["pt-BR"]) == placeholders(loaded["en"])
    for key in loaded["en"]:
        if key.startswith(("findings.", "home.f1", "home.f2", "home.f3")):
            assert placeholders({key: loaded["en"][key]}) == placeholders({key: loaded["pt-BR"][key]}), key


def test_every_band_has_findings_in_both_locales() -> None:
    for locale, strings in i18n.load_locales().items():
        for band in BANDS:
            keys = [k for k in strings if k.startswith(f"findings.{bands.key(band)}.p.")]
            assert 2 <= len(keys) <= 3, (locale, band, keys)  # the spec asks for two or three sentences


def test_partial_findings_say_so() -> None:
    """The brief: where a finding is partial the text must say so, never promise "all bands but one"."""
    en = i18n.load_locales()["en"]
    assert "weakly" in en["home.f1.h"] and "did not settle either" in en["home.f2.h"]
    assert "Linkin Park" in en["home.f2.p.1"] and "It did not fall for Linkin Park" in en["home.f2.p.1"]
    assert "short, censored curve" in en["home.f3.p.4"] and "Dig Out Your Soul" in en["home.f3.p.4"]
    # Cross-band comparison is at a common horizon; the end-of-history values are a per-band detail.
    assert "same horizon" in en["home.f3.p.1"] and "not a ranking" in en["home.f3.p.2"]
    assert "500 shows" in en["methodology.survival.p.4"] and "longer career" in en["methodology.survival.p.4"]
    assert "the high end" not in " ".join(en.values())
    assert "does not show that the release caused it" in en["home.f1.p.3"]
    assert "2000s" not in " ".join(en.values())  # the "2000s albums below 30%" claim was dropped


def _real_marts():
    if not os.environ.get("POSTGRES_USER") or not os.environ.get("POSTGRES_PASSWORD"):
        pytest.skip("no database credentials in the environment")
    try:
        return marts_mod.load_all()
    except Exception as exc:  # no database reachable: this check needs the real marts
        pytest.skip(f"real marts unavailable: {exc}")


@pytest.fixture(scope="module")
def real():
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    return _real_marts()


def test_the_real_data_fills_every_placeholder_in_both_locales(real, tmp_path: Path) -> None:
    from datetime import date
    build.build_site(real, tmp_path / "site", built_on=date(2026, 9, 24), origin="https://example.test")


def test_the_claims_in_the_text_hold_on_the_real_data(real) -> None:
    """The text asserts directions and orderings; if new data reverses one, this fails before the text ships."""
    age, rot = real["mart_repertoire_age"], real["mart_band_rotation_by_year"]
    curves, summary = real["mart_survival_curves"], real["mart_survival_summary"]

    # 01: Metallica dips clearly after each of its three latest albums; the others are small or absent.
    def dip(band: str, before: int, low: int) -> float:
        s = shape.age_by_year(age, band).set_index("show_year")["avg_age"]
        return float(s[before] - s[low])

    for before, low in ((2007, 2009), (2015, 2018), (2022, 2023)):
        assert dip("Metallica", before, low) > 4
    assert 0 < dip("Avenged Sevenfold", 2009, 2010) < 1.5 and 0 < dip("Avenged Sevenfold", 2012, 2013) < 1.5
    assert dip("Avenged Sevenfold", 2015, 2016) < 0  # The Stage: no dip
    assert 0 < dip("Linkin Park", 2006, 2007) < 2 and 0 < dip("Linkin Park", 2009, 2010) < 2
    assert dip("Linkin Park", 2011, 2012) < 0  # Living Things: no dip

    # 02: rotation fell for five bands, did not fall for Linkin Park, rose for Metallica.
    def ends(band: str) -> tuple[float, float]:
        r = shape.rotation_by_year(rot, band)
        r = r[~r.thin]
        return float(r.head(3).rotation.mean()), float(r.tail(3).rotation.mean())

    for band in ("Arctic Monkeys", "Oasis", "Twenty One Pilots", "Muse", "Avenged Sevenfold"):
        first, last = ends(band)
        assert last < first, band
    first, last = ends("Linkin Park")
    assert last >= first
    first, last = ends("Metallica")
    assert last > 3 * first
    tours = real["mart_tour_rotation"].set_index(["band", "tour_name"])["rotation"]
    assert 0.74 < tours[("Metallica", "M72 World Tour")] < 0.76
    assert 0.84 < float(shape.rotation_by_year(rot, "Metallica").set_index("show_year").rotation[2024]) < 0.87

    # 03: at the common horizon every curve is compared at the same point; the ranking is read there.
    horizon = shape.COMMON_HORIZON
    at = {b: shape.survival_at(curves, b, "all", horizon) for b in bands.band_names()}
    assert all(v is not None for v in at.values()), "every band's curve must reach the common horizon"
    assert min(v[1] for v in at.values()) == min(at["Linkin Park"][1], at["Arctic Monkeys"][1]) >= 20  # songs still followed
    assert sorted(at, key=lambda b: at[b][0], reverse=True) == [
        "Metallica", "Twenty One Pilots", "Avenged Sevenfold", "Muse", "Arctic Monkeys", "Oasis", "Linkin Park"]
    assert at["Linkin Park"][1] == min(v[1] for v in at.values())  # the "at least N songs" figure quoted in the text
    assert 0.38 < at["Linkin Park"][0] < 0.40 and 0.66 < at["Metallica"][0] < 0.68
    # The end-of-history values are quoted per band only; a longer follow-up ends lower (Oasis vs Muse).
    ends = {b: shape.final_survival(curves, b) for b in bands.band_names()}
    assert ends["Oasis"][0] < ends["Muse"][0] and 0.35 < ends["Oasis"][1] < 0.37 and ends["Oasis"][1] < at["Oasis"][0]
    mg = shape.final_survival(curves, "Oasis", "(What’s the Story) Morning Glory?")
    assert mg[1] > 0.85
    doys = shape.final_survival(curves, "Oasis", "Dig Out Your Soul")
    songs = shape.album_table(summary, "Oasis").set_index("album").loc["Dig Out Your Soul", "songs"]
    assert doys[0] < 200 and songs <= 6
