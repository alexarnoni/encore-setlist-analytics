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


DECADE = re.compile(r"\b(?:19|20)\d0s?\b")  # "the 1980s" / "anos 1980" is a decade, not a figure
SENTENCE_END = re.compile(r"[.!?](?:\s|$)")


def layer_one() -> dict[str, dict[str, str]]:
    """Every plain-language lead of the site, per locale: home headings, the added concrete sentence, band leads."""
    out = {}
    for locale, strings in i18n.load_locales().items():
        keys = [k for k in strings if k in ("home.f1.h", "home.f2.h", "home.f2.lead_more", "home.f3.h")
                or (k.startswith("findings.") and k.endswith(".lead"))]
        out[locale] = {k: strings[k] for k in keys}
    return out


def test_layer_one_is_plain_language_with_no_numbers_or_placeholders() -> None:
    for locale, leads in layer_one().items():
        assert len(leads) == 4 + len(BANDS), locale  # 3 headings + 1 concrete sentence + 7 band leads
        for key, text in leads.items():
            assert "{{" not in text and not re.search(r"\d", DECADE.sub("", text)), (locale, key, text)


def test_every_finding_has_its_three_layers_in_both_locales() -> None:
    for locale, strings in i18n.load_locales().items():
        for f in ("f1", "f2", "f3"):
            assert strings[f"home.{f}.h"] and strings[f"home.{f}.numbers"], (locale, f)
            assert any(k.startswith(f"home.{f}.caveats.") for k in strings), (locale, f)
        for band in BANDS:
            k = bands.key(band)
            assert strings[f"findings.{k}.lead"] and strings[f"findings.{k}.numbers"], (locale, band)
            assert any(key.startswith(f"findings.{k}.caveats.") for key in strings), (locale, band)
            sentences = len(SENTENCE_END.findall(strings[f"findings.{k}.numbers"]))
            assert 2 <= sentences <= 4, (locale, band, sentences)  # two or three sentences with the key numbers
        assert strings["findings.common"] and strings["caveats.summary"]


def test_every_chart_kind_has_a_reading_line_in_both_locales() -> None:
    for locale, strings in i18n.load_locales().items():
        for kind in ("age", "rotation", "rotation_small", "tours", "survival"):
            assert len(strings[f"read.{kind}"]) > 60, (locale, kind)
        assert strings["read.label"]


def test_partial_findings_say_so() -> None:
    """The brief: where a finding is partial the text says so, and never promises "all bands but one"."""
    en = i18n.load_locales()["en"]
    assert "only a hint for the other two" in en["home.f1.numbers"]
    assert "does not show that the release caused it" in " ".join(v for k, v in en.items() if k.startswith("home.f1.caveats"))
    assert en["home.f2.h"].startswith("Most of these bands") and "all bands" not in en["home.f2.h"]
    assert "It did not fall for Linkin Park" in en["home.f2.numbers"]
    assert "short, censored curve" in en["home.f3.caveats.3"] and "Dig Out Your Soul" in en["home.f3.caveats.3"]
    assert "not a ranking" in en["home.f3.caveats.1"] and "same horizon" not in en["home.f3.h"]
    assert "500 shows" in en["methodology.survival.p.4"] and "longer career" in en["methodology.survival.p.4"]
    assert "the high end" not in " ".join(en.values()) and "2000s" not in " ".join(en.values())


def test_the_concrete_sentence_for_finding_two_only_claims_what_the_data_supports() -> None:
    """The marts have no city or per-show data and consecutive M72 shows overlap by about a quarter, so the text
    must say "a substantially different set", never "no repeated songs" or "two shows in the same city"."""
    for locale, strings in i18n.load_locales().items():
        sentence = strings["home.f2.lead_more"].lower()
        assert "same city" not in sentence and "mesma cidade" not in sentence, locale
        assert "without repeating" not in sentence and "sem repetir" not in sentence, locale
    en = i18n.load_locales()["en"]["home.f2.lead_more"]
    assert "substantially different set" in en and "nearly the same songs" in en


def test_the_hero_of_finding_three_is_morning_glory_and_the_oasis_horizon_figure_is_in_the_numbers() -> None:
    en = i18n.load_locales()["en"]
    assert "Morning Glory" in en["home.f3.stat_label"]
    assert "{{ oasis_surv_500 }} for Oasis" in en["home.f3.numbers"]


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
    overlap = real["mart_tour_rotation"].set_index(["band", "tour_name"])["mean_jaccard"]
    assert overlap[("Metallica", "M72 World Tour")] < 0.3  # "a substantially different set"
    assert overlap[("Metallica", "Damaged Justice")] > 0.8 and overlap[("Metallica", "Kill 'Em All for One")] > 0.9
    assert overlap[("Metallica", "M72 World Tour")] > 0.1  # consecutive M72 shows do overlap, so "no repeated songs" would be false
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


# ---- plain language: what a first-time reader meets (docs: the site must not assume concert or statistics jargon)
READER_FACING = ("home.", "comparison.", "band.", "findings.", "read.", "caveats.", "chart.", "labels.", "footer.", "site.")
METHODOLOGY_ONLY_TERMS = re.compile(r"performance|execuç|execuc", re.I)


def test_the_home_lede_says_what_the_data_is_before_what_is_measured() -> None:
    for locale, strings in i18n.load_locales().items():
        lede = strings["home.lede"]
        order = ["setlist.fm", "MusicBrainz"]
        assert all(word in lede for word in order), locale
        assert lede.index("setlist.fm") < lede.index("MusicBrainz") < lede.index(
            "três coisas" if locale == "pt-BR" else "three things"), locale
        assert 2 <= len(SENTENCE_END.findall(lede)) <= 3, locale  # two or three sentences
    en = i18n.load_locales()["en"]["home.lede"]
    assert "concerts" in en and "fans fill them in" in en and en.index("setlist") < en.index("three things")
    pt = i18n.load_locales()["pt-BR"]["home.lede"]
    assert "shows" in pt and "preenchido por fãs" in pt


def test_each_metric_is_explained_in_concert_terms_before_its_name_on_the_home_page() -> None:
    en, pt = i18n.load_locales()["en"], i18n.load_locales()["pt-BR"]
    assert en["home.f1.numbers"].startswith("Repertoire age is how old the songs played")
    assert en["home.f2.numbers"].startswith("Rotation is how much the songs change from one concert to the next")
    assert en["home.f3.numbers"].startswith("Survival is how long a song keeps being played at concerts")
    assert pt["home.f1.numbers"].startswith("A idade do repertório é quão antigas eram as músicas tocadas")
    assert pt["home.f2.numbers"].startswith("A rotação é o quanto as músicas mudam de um show para o seguinte")
    assert pt["home.f3.numbers"].startswith("A sobrevivência é quanto tempo uma música continua sendo tocada")
    # The labels above the findings speak in concert terms; the metric names come after the plain phrase.
    for strings in (en, pt):
        for kicker in ("home.f1.kicker", "home.f2.kicker", "home.f3.kicker"):
            assert not re.search(r"repertoire age|rotation|survival|idade do repertório|rotação|sobrevivência", strings[kicker], re.I)
        for key in ("comparison.age.h", "comparison.rotation.h", "comparison.survival.h", "band.age.h", "band.rotation.h", "band.survival.h"):
            assert ":" in strings[key], key  # "plain phrase: metric name"


def test_band_pages_and_the_comparison_page_open_with_what_the_data_is() -> None:
    for locale, strings in i18n.load_locales().items():
        assert "setlist.fm" in strings["band.intro"] and "MusicBrainz" in strings["band.intro"], locale
        assert "setlist.fm" in strings["comparison.lede"], locale
        assert "median" in strings["band.chip_median"].lower() or "mediana" in strings["band.chip_median"].lower()
        assert strings["band.chip_median"].index("{{ n }}") < strings["band.chip_median"].lower().index("median")  # plain phrase first


def test_the_discography_and_the_musicbrainz_match_are_never_both_called_the_catalog() -> None:
    loaded = i18n.load_locales()
    assert not [k for k, v in loaded["en"].items() if re.search(r"catalog", v, re.I)]
    assert not [k for k, v in loaded["pt-BR"].items() if re.search(r"catálogo|catalogo", v, re.I)]
    en, pt = loaded["en"], loaded["pt-BR"]
    assert "MusicBrainz" in en["labels.matched_rate"] and "MusicBrainz" in pt["labels.matched_rate"]
    assert "MusicBrainz" in en["band.chip_match"] and "MusicBrainz" in pt["band.chip_match"]
    assert "discography" in en["home.title"] and "discografia" in pt["home.title"]


def test_censored_never_appears_without_a_plain_gloss() -> None:
    gloss = re.compile(r"still (?:being )?played|came back|returned|ainda (?:são )?tocadas?|voltaram|voltou", re.I)
    for locale, strings in i18n.load_locales().items():
        for key, text in strings.items():
            if re.search(r"censor", text, re.I):
                assert gloss.search(text), (locale, key)


def test_performances_is_kept_for_the_methodology_page_only() -> None:
    allowed = ("methodology.", "labels.performances", "about.stack")
    for locale, strings in i18n.load_locales().items():
        for key, text in strings.items():
            if key.startswith(allowed):
                continue
            assert not METHODOLOGY_ONLY_TERMS.search(text), (locale, key, text[:80])


def test_the_hero_number_of_finding_one_has_a_short_label() -> None:
    for locale, strings in i18n.load_locales().items():
        assert len(strings["home.f1.stat_label"]) <= 75, (locale, strings["home.f1.stat_label"])
        assert "{{" not in strings["home.f1.stat_label"]  # the before and after values moved into the numbers paragraph
    for locale, strings in i18n.load_locales().items():
        assert "dip_metallica_72_seasons_before" in strings["home.f1.numbers"] and "dip_metallica_72_seasons_low" in strings["home.f1.numbers"]
