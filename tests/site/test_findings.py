"""T12: the hand-written findings only quote figures the build can supply, and their claims hold on real data."""

import os
import re
from pathlib import Path

import pytest

from encore.site import bands, build, i18n, marts as marts_mod, shape, values
from tests.site.fixtures import BANDS, fake_marts

# Placeholders a template fills at call time (the caller passes them), not from the marts.
CALL_TIME = {"min_pairs", "min_songs", "min_tour_shows", "n_window", "n", "band", "first", "last", "pct",
             "setlistfm_url", "musicbrainz_url", "repo_url", "author_url",
             "cal", "cal_100", "median", "median_cal", "per_year"}


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


def test_each_chart_has_one_explanation_and_no_separate_reading_line() -> None:
    """The paragraph before a chart is the only explanation: mechanics plus what counts as low and high."""
    for locale, strings in i18n.load_locales().items():
        assert not [k for k in strings if k.startswith("read.")], locale
        explanations = [f"home.f{n}.explain" for n in (1, 2, 3)] + [
            f"{page}.{kind}.p" for page in ("comparison", "band") for kind in ("age", "rotation", "survival")]
        for key in explanations:
            assert len(strings[key]) > 120, (locale, key)
        scale_0_5 = "0,5" if locale == "pt-BR" else "0.5"
        for key in ("home.f2.explain", "comparison.rotation.p", "band.rotation.p"):
            assert "0" in strings[key] and scale_0_5 in strings[key], (locale, key)  # near 0 = same show, above 0.5 = half change
        assert "{{ oasis_surv_median_cal }}" in strings["home.f3.explain"]  # the median is anchored in calendar terms
        assert "{{ median_cal }}" in strings["band.survival.median"] and "{{ cal_100 }}" in strings["band.survival.p"]


def test_each_chart_kind_says_whose_line_it_is_on_its_own_page() -> None:
    """Band pages plot one band, so they never say "each line is one band" (the comparison and home pages may)."""
    for locale, strings in i18n.load_locales().items():
        for key in ("band.age.p", "band.rotation.p", "band.survival.p"):
            assert not re.search(r"cada linha é uma banda|each line is one band|cada quadro|each panel", strings[key], re.I), (locale, key)
        assert "{{ band }}" in strings["band.age.p"] and "{{ band }}" in strings["band.rotation.p"]


FIGURE_BUDGET = 4  # a "numbers" paragraph carries at most this many figures; charts and tables hold the rest
NOT_A_FIGURE = re.compile(r"(_years|_cal)$")


def figures(text: str) -> set[str]:
    """Figures a paragraph quotes: placeholders except year lists, calendar equivalents and the size of a fraction."""
    names = {n for n in re.findall(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}", text) if not NOT_A_FIGURE.search(n)}
    return {n for n in names if not n.endswith("_songs")}  # "9 de 11" is one figure


def test_numbers_paragraphs_carry_few_figures() -> None:
    for locale, strings in i18n.load_locales().items():
        keys = ["home.f1.numbers", "home.f2.numbers", "home.f3.numbers"] + [
            f"findings.{bands.key(b)}.numbers" for b in BANDS]
        for key in keys:
            assert len(figures(strings[key])) <= FIGURE_BUDGET, (locale, key, sorted(figures(strings[key])))


def test_every_band_has_a_context_line_marked_as_not_proven_by_the_data() -> None:
    for locale, strings in i18n.load_locales().items():
        label = strings["band.context_label"].lower()
        assert ("não algo que os dados provam" if locale == "pt-BR" else "not something the data proves") in label
        for band in BANDS:
            context = strings[f"findings.{bands.key(band)}.context"]
            assert context and "{{" not in context, (locale, band)
    en = i18n.load_locales()["en"]
    # The Rev's death and the change of sound are stated side by side, without a causal link to the rotation drop.
    context = en["findings.avenged_sevenfold.context"]
    assert "The Rev died" in context and "sound changed" in context
    assert not re.search(r"because|caused|led to|explains|therefore", context, re.I)


def test_calendar_equivalents_are_marked_approximate_and_rounded() -> None:
    assert i18n.fmt_span(674, 54.9, "pt-BR") == "cerca de 12 anos" and i18n.fmt_span(674, 54.9, "en") == "about 12 years"
    assert i18n.fmt_span(100, 55, "en") == "about 2 years"  # 1.8 years: whole years from 1.5 up
    assert i18n.fmt_span(45, 55, "en") == "about 10 months" and i18n.fmt_span(45, 55, "pt-BR") == "cerca de 10 meses"
    assert i18n.fmt_span(5, 55, "en") == "about 1 month" and i18n.fmt_span(5, 55, "pt-BR") == "cerca de 1 mês"
    from datetime import date
    assert i18n.fmt_date(date(2026, 9, 23), "pt-BR") == "23/09/2026" and i18n.fmt_date(date(2026, 9, 3), "en") == "3 Sep 2026"
    en = values.placeholder_values(fake_marts(), tuple(BANDS), "en")
    assert re.fullmatch(r"about \d+ (years|months?)", en["muse_surv_median_cal"]) and int(en["muse_surv_per_year"]) > 0


def test_albums_named_like_their_band_are_disambiguated_for_the_reader() -> None:
    loaded = i18n.load_locales()
    assert loaded["pt-BR"]["album_labels.twenty_one_pilots.twenty_one_pilots"] == "Twenty One Pilots (álbum de estreia)"
    assert loaded["en"]["album_labels.twenty_one_pilots.twenty_one_pilots"] == "Twenty One Pilots (debut album)"
    assert "estreia" not in loaded["pt-BR"]["album_labels.metallica.metallica"]  # Metallica's self-titled album is not a debut
    assert "álbum de estreia Twenty One Pilots" in loaded["pt-BR"]["findings.twenty_one_pilots.numbers"]


def test_partial_findings_say_so() -> None:
    """The brief: where a finding is partial the text says so, and never promises "all bands but one"."""
    en = i18n.load_locales()["en"]
    assert "only a hint for the other two" in en["home.f1.numbers"]
    assert "does not show that the release caused it" in " ".join(v for k, v in en.items() if k.startswith("home.f1.caveats"))
    assert en["home.f2.h"].startswith("Most of these bands") and "all bands" not in en["home.f2.h"]
    assert "fell for five of the seven bands" in en["home.f2.numbers"]
    assert "It did not fall for Linkin Park" in en["home.f2.caveats.4"]
    assert "censored curve" in en["home.f3.caveats.4"] and "Dig Out Your Soul" in en["home.f3.caveats.4"]
    assert "not a ranking" in en["home.f3.caveats.2"] and "same horizon" not in en["home.f3.h"]
    assert "500 shows" in en["methodology.survival.p.4"] and "longer career" in en["methodology.survival.p.4"]
    # The context lines are outside the data's claims (approved wording: "since the 2000s"); everything else stays clear of it.
    claims = " ".join(v for k, v in en.items() if not (k.startswith("findings.") and k.endswith(".context")))
    assert "the high end" not in claims and "2000s" not in claims


def test_the_no_repeat_weekend_format_is_presented_as_context_the_data_cannot_confirm() -> None:
    """The marts have no city or per-show data. The lead sentence claims only "substantially different sets, partly by
    design"; the format itself appears in the caveats, labelled as public context, next to the World Magnetic limit."""
    for locale, strings in i18n.load_locales().items():
        sentence = strings["home.f2.lead_more"].lower()
        assert "same city" not in sentence and "mesma cidade" not in sentence, locale
        assert "without repeating" not in sentence and "sem repetir" not in sentence, locale
    en, pt = i18n.load_locales()["en"], i18n.load_locales()["pt-BR"]
    assert "substantially different sets" in en["home.f2.lead_more"] and "nearly the same songs" in en["home.f2.lead_more"]
    for strings, words in ((en, ("No Repeat Weekend", "public context", "neither confirms nor rules out", "does not explain everything")),
                           (pt, ("No Repeat Weekend", "contexto público", "não confirmam nem descartam", "não explica tudo"))):
        caveats = " ".join(v for k, v in strings.items() if k.startswith("home.f2.caveats."))
        assert all(w in caveats for w in words)
        band_caveats = " ".join(v for k, v in strings.items() if k.startswith("findings.metallica.caveats."))
        assert all(w in band_caveats for w in words)
        assert "No Repeat Weekend" in strings["findings.metallica.context"]


def test_the_hero_of_finding_three_is_morning_glory_and_the_horizon_figures_are_in_the_caveats() -> None:
    en = i18n.load_locales()["en"]
    assert "Morning Glory" in en["home.f3.stat_label"]
    assert "Oasis {{ oasis_surv_500 }}" in en["home.f3.caveats.7"]


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
    # The M72 framing: the highest rotation of any Metallica tour, no song in 9 of 10 shows, and World Magnetic already high.
    metallica_tours = real["mart_tour_rotation"][real["mart_tour_rotation"]["band"] == "Metallica"]
    assert metallica_tours.set_index("tour_name")["rotation"].idxmax() == "M72 World Tour"
    assert int(metallica_tours.set_index("tour_name").loc["M72 World Tour", "core_songs"]) == 0
    assert tours[("Metallica", "World Magnetic")] > 0.5
    assert max(tours[("Metallica", t)] for t in ("Damaged Justice", "Damage Inc.", "Ride the Lightning")) < 0.18  # "no 1980s tour above 0.17"
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
    assert en["home.f1.explain"].startswith("Repertoire age is how old the songs played")
    assert en["home.f2.explain"].startswith("Rotation measures how much the setlist changes from one show to the next")
    assert en["home.f3.explain"].startswith("Survival is how long a song keeps being played at concerts")
    assert pt["home.f1.explain"].startswith("A idade do repertório é quão antigas eram as músicas tocadas")
    assert pt["home.f2.explain"].startswith("Rotação mede o quanto o setlist muda de um show para o seguinte")
    assert pt["home.f3.explain"].startswith("A sobrevivência é quanto tempo uma música continua sendo tocada")
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


def test_eligible_songs_is_glossed_at_first_use_on_every_band_page() -> None:
    """"Eligible" is a technical filter (see Methodology): its first use in a band's text explains it inline."""
    for locale, strings in i18n.load_locales().items():
        word = "eligible songs" if locale == "en" else "músicas elegíveis"
        for band in BANDS:
            text = strings[f"findings.{bands.key(band)}.numbers"]
            if word not in text:
                continue
            after = text[text.index(word) + len(word):]
            assert after.startswith(" ("), (locale, band)  # "eligible songs (those played at least 3 times ...)"
            assert "3" in after[:80] and "MusicBrainz" in after[:120], (locale, band)
            assert text.count(word) == 1 or "(" not in text[text.rindex(word) + len(word):][:3], (locale, band)  # only the first is glossed


def test_the_home_hero_label_of_finding_three_stands_on_its_own() -> None:
    for locale, strings in i18n.load_locales().items():
        label = strings["home.f3.stat_label"]
        assert "elegíve" not in label and "eligible" not in label, locale
        assert not re.match(r"(of|das) the \d|das \{\{ *\w*songs", label), locale  # no "das 9 ..." under a big number
        assert "{{ oasis_album_whats_the_story_morning_glory_songs }}" not in label, locale
    en, pt = i18n.load_locales()["en"], i18n.load_locales()["pt-BR"]
    assert en["home.f3.stat_label"].startswith("of the songs on (What's the Story) Morning Glory?")
    assert pt["home.f3.stat_label"].startswith("das músicas de (What's the Story) Morning Glory?")
    assert "3 times" in en["home.f3.caveats.6"] and "3 vezes" in pt["home.f3.caveats.6"]  # the counting rule stays visible


def test_the_abandonment_definition_uses_plain_wording() -> None:
    for locale, strings in i18n.load_locales().items():
        text = strings["methodology.survival.p.2"]
        assert not re.search(r"performance|execuç|execuc", text, re.I), locale
        assert ("played at least 3 times in total" in text) or ("tocadas pelo menos 3 vezes no total" in text), locale
