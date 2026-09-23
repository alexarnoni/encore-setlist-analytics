"""T4: aggregations against hand-computed values, on the fixture and on small custom frames."""

import math

import pandas as pd
import pytest

from encore.site import bands, shape, values
from tests.site.fixtures import BANDS, fake_marts


@pytest.fixture(scope="module")
def marts():
    return fake_marts()


def test_band_names_come_from_config_in_order() -> None:
    assert bands.band_names() == tuple(BANDS)
    assert bands.slug("Twenty One Pilots") == "twenty-one-pilots"
    assert bands.key("Avenged Sevenfold") == "avenged_sevenfold"


def test_age_by_year_is_weighted_by_aged_performances() -> None:
    age = pd.DataFrame({
        "band": ["X", "X", "X", "Y"], "tour_name": ["A", "B", "C", "A"], "show_year": [2001, 2001, 2002, 2001],
        "aged_performances": [100, 300, 50, 10], "avg_repertoire_age": [10.0, 20.0, 5.0, 99.0],
    })
    out = shape.age_by_year(age, "X")
    assert list(out["show_year"]) == [2001, 2002]
    assert out["avg_age"].tolist() == [pytest.approx(17.5), pytest.approx(5.0)]  # (1000+6000)/400
    assert out["aged_performances"].tolist() == [400, 50]


def test_age_by_year_skips_cells_without_age() -> None:
    age = pd.DataFrame({"band": ["X", "X"], "tour_name": ["A", "B"], "show_year": [2001, 2001],
                        "aged_performances": [0, 40], "avg_repertoire_age": [None, 8.0]})
    assert shape.age_by_year(age, "X")["avg_age"].tolist() == [8.0]


def test_age_by_tour_cell_drops_unknown_and_thin_cells(marts) -> None:
    age = pd.DataFrame({
        "band": ["X"] * 4, "tour_name": ["Big", "Small", "Unknown tour", "Big"], "show_year": [2001, 2001, 2001, 2002],
        "shows": [30, 4, 50, 20], "median_repertoire_age": [7.0, 1.0, 9.0, None], "avg_repertoire_age": [8.0, 1.0, 9.0, 3.0],
    })
    out = shape.age_by_tour_cell(age, "X")
    assert out[["tour_name", "show_year", "median_age"]].values.tolist() == [["Big", 2001, 7.0]]
    fixture_cells = shape.age_by_tour_cell(marts["mart_repertoire_age"], "Muse", min_shows=10)
    assert len(fixture_cells) == 5 and fixture_cells["median_age"].iloc[0] == 4.0 + 4  # Muse is band 4


def test_rotation_by_year_flags_thin_years() -> None:
    rot = pd.DataFrame({"band": ["X"] * 3, "show_year": [2003, 2001, 2002], "rotation": [0.1, 0.2, 0.3], "pairs": [40, 5, 4]})
    out = shape.rotation_by_year(rot, "X")
    assert list(out["show_year"]) == [2001, 2002, 2003]
    assert out["thin"].tolist() == [False, True, False]  # 5 pairs is enough, 4 is not


def test_survival_albums_and_album_table(marts) -> None:
    summary = marts["mart_survival_summary"]
    assert shape.survival_albums(summary, "Oasis") == ["Album One", "Album Two", "non-album"]
    table = shape.album_table(summary, "Oasis")
    assert table["album"].tolist() == ["all", "Album One", "Album Two", "non-album"]
    assert table.loc[0, ["songs", "abandoned", "censored"]].tolist() == [30, 15, 15]
    assert math.isnan(table.loc[3, "median"])
    assert table.loc[1, "median"] == 100.0 + 50 + 1  # Oasis is band 1
    assert not table["small"].any()


def test_small_albums_are_flagged_not_drawn() -> None:
    summary = pd.DataFrame({
        "band": ["X"] * 3, "album": ["Big", "Tiny", "all"], "n_window": [50] * 3, "songs": [12, 4, 16],
        "events": [5, 1, 6], "censored": [7, 3, 10], "median_survival_shows": [90.0, None, 80.0],
    })
    assert shape.survival_albums(summary, "X") == ["Big"]
    table = shape.album_table(summary, "X")
    assert dict(zip(table["album"], table["small"])) == {"all": False, "Big": False, "Tiny": True}


def test_km_curve_starts_at_zero(marts) -> None:
    c = shape.km_curve(marts["mart_survival_curves"], "Oasis", "all")
    assert c.iloc[0].tolist() == [0, 1.0, 1.0, 1.0]
    assert c["t_shows"].is_monotonic_increasing and len(c) == 6


def test_median_and_sensitivity_tables(marts) -> None:
    t = shape.median_table(marts["mart_survival_summary"], tuple(BANDS))
    assert t["band"].tolist() == BANDS
    assert t["median"].tolist() == [150.0 + b for b in range(7)]
    s = shape.sensitivity_table(marts["mart_survival_summary"], tuple(BANDS))
    assert s.columns.tolist() == ["band", 25, 50, 100]
    assert s.loc[2].tolist() == ["Linkin Park", 127.0, 152.0, 202.0]


def test_match_by_band_is_weighted_by_performances() -> None:
    q = pd.DataFrame({
        "band": ["X", "X"], "show_year": [2001, 2002], "performances": [100, 300], "matched_performances": [90, 300],
        "match_rate_by_performance": [0.9, 1.0], "match_rate_by_album": [0.5, 0.9],
    })
    out = shape.match_by_band(q, ("X",)).iloc[0]
    assert out["rate"] == pytest.approx(390 / 400)
    assert out["rate_album"] == pytest.approx((50 + 270) / 400)
    assert (out["first_year"], out["last_year"]) == (2001, 2002)


def test_weakest_years_uses_threshold() -> None:
    q = pd.DataFrame({"band": ["Muse"] * 3, "show_year": [1994, 1995, 1996], "performances": [9, 50, 400],
                      "matched_performances": [0, 12, 399], "match_rate_by_performance": [0.0, 0.24, 0.9975]})
    out = shape.weakest_years(q, "Muse")
    assert out["show_year"].tolist() == [1994, 1995]


def test_shows_and_touring_intensity(marts) -> None:
    assert shape.shows_by_band(marts["mart_repertoire_age"])["Muse"] == 5 * 14
    assert shape.touring_intensity(marts["mart_band_rotation_by_year"], since=2002)["Oasis"] == 25.0  # (3 x 21 + 2 x 31) / 5 active years


def test_placeholder_values_per_locale(marts) -> None:
    en = values.placeholder_values(marts, tuple(BANDS), "en")
    pt = values.placeholder_values(marts, tuple(BANDS), "pt-BR")
    assert en["metallica_median"] == "155" and en["twenty_one_pilots_songs"] == "30"
    assert en["muse_match"] == "92.9%" and pt["muse_match"] == "92,9%"  # (5*380 + 0 + 12) / (5*400 + 9 + 50)
    assert en["oasis_match"] == "95.0%"
    assert en["oasis_first_year"] == "2000" and en["bands_count"] == "7"
    assert en["shows_total"] == pt["shows_total"] == str(sum(5 * (10 + b) for b in range(7)))


def test_placeholder_without_a_value_is_left_out() -> None:
    m = fake_marts()
    s = m["mart_survival_summary"]
    m["mart_survival_summary"] = s.assign(median_survival_shows=s["median_survival_shows"].where(s["band"] != "Muse"))
    out = values.placeholder_values(m, tuple(BANDS), "en")
    assert "muse_median" not in out and "oasis_median" in out


def test_methodology_placeholders_from_the_marts(marts) -> None:
    en = values.placeholder_values(marts, tuple(BANDS), "en")
    pt = values.placeholder_values(marts, tuple(BANDS), "pt-BR")
    assert (en["muse_1994_performances"], en["muse_1994_matched"], en["muse_1995_rate"]) == ("9", "0", "24.0%")
    assert en["muse_weak_share"] == "2.87%" and pt["muse_weak_share"] == "2,87%"  # 59 of 2,059
    assert "oasis_weak_share" not in en  # no weak year, so a text that uses it fails the build
    assert en["muse_pairs_avg"] == "34" and en["muse_pairs_max"] == "34"  # 30 + band index 4, in 2015-2016
    assert en["band_list"].startswith("Arctic Monkeys, Oasis")


def test_largest_age_drop_uses_consecutive_years_only() -> None:
    age = pd.DataFrame({
        "band": ["X"] * 5, "tour_name": ["A"] * 5, "show_year": [2000, 2001, 2003, 2004, 2005],
        "aged_performances": [10] * 5, "avg_repertoire_age": [10.0, 12.0, 5.0, 9.0, 6.0],
    })
    drop = shape.largest_age_drop(age, "X")
    # 2001 -> 2003 skips a year and does not count; 2004 -> 2005 falls by 3.0.
    assert drop == {"year_prev": 2004, "year": 2005, "age_from": 9.0, "age_to": 6.0, "drop": 3.0}
    rising = age.assign(avg_repertoire_age=[1.0, 2.0, 3.0, 4.0, 5.0])
    assert shape.largest_age_drop(rising, "X") is None


def test_final_survival_and_hero_drop_is_consistent_with_rounded_ends(marts) -> None:
    assert shape.final_survival(marts["mart_survival_curves"], "Oasis") == (50, pytest.approx(0.25))
    assert shape.final_survival(marts["mart_survival_curves"], "Nobody") is None
    m = fake_marts()
    m["mart_repertoire_age"] = m["mart_repertoire_age"].assign(
        avg_repertoire_age=lambda d: d["avg_repertoire_age"] + (d["show_year"] == 2002) * 0.04
        + (d["show_year"] == 2003) * 0.06)
    en = values.placeholder_values(m, tuple(BANDS), "en")
    # 12.04 -> 10.06 is a 1.98 fall, but the page prints "12.0" and "10.1", so it must print 1.9, not 2.0.
    assert (en["f1_from"], en["f1_to"], en["f1_drop"]) == ("12.0", "10.1", "1.9")
