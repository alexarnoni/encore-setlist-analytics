"""T3: locale parity, strict keys, strict placeholders, number formatting."""

from pathlib import Path

import pytest

from encore.site import i18n
from encore.site.i18n import LocaleError, Translator


def _write(directory: Path, locale: str, text: str) -> None:
    (directory / f"{locale}.yml").write_text(text, encoding="utf8")


def test_shipped_locales_have_identical_keys() -> None:
    loaded = i18n.load_locales()
    assert set(loaded) == {"pt-BR", "en"}
    assert set(loaded["pt-BR"]) == set(loaded["en"])
    assert all(v.strip() for strings in loaded.values() for v in strings.values())


def test_key_only_in_one_locale_fails(tmp_path: Path) -> None:
    _write(tmp_path, "pt-BR", "a: um\nb: dois\n")
    _write(tmp_path, "en", "a: one\n")
    with pytest.raises(LocaleError, match="missing"):
        i18n.load_locales(tmp_path)


def test_missing_locale_file_fails(tmp_path: Path) -> None:
    _write(tmp_path, "pt-BR", "a: um\n")
    with pytest.raises(LocaleError, match="missing locale file"):
        i18n.load_locales(tmp_path)


def test_non_string_value_fails(tmp_path: Path) -> None:
    _write(tmp_path, "pt-BR", "a: 3\n")
    _write(tmp_path, "en", "a: 3\n")
    with pytest.raises(LocaleError, match="must be strings"):
        i18n.load_locales(tmp_path)


def test_missing_key_lookup_fails() -> None:
    t = Translator("en", {"a": "x"})
    assert t("a") == "x"
    with pytest.raises(LocaleError, match="missing translation key: nope"):
        t("nope")


def test_placeholder_is_filled_and_value_escaped() -> None:
    t = Translator("en", {"f": "Median: {{ n }} for {{ band }}."}, {"n": "1,235", "band": "<b>x</b>"})
    assert t("f") == "Median: 1,235 for &lt;b&gt;x&lt;/b&gt;."


def test_locale_markup_is_kept() -> None:
    t = Translator("en", {"f": 'See <a href="/x/">this</a>.'})
    assert t("f") == 'See <a href="/x/">this</a>.'


def test_unfilled_placeholder_fails() -> None:
    t = Translator("en", {"f": "Median: {{ metallica_median }}"})
    with pytest.raises(LocaleError, match="unfilled placeholder"):
        t("f")
    assert t("f", metallica_median="1235") == "Median: 1235"


def test_bad_placeholder_syntax_fails() -> None:
    with pytest.raises(LocaleError, match="bad placeholder syntax"):
        Translator("en", {"f": "{{ oops "})("f")


def test_section_returns_keys_in_order_and_fails_when_empty() -> None:
    t = Translator("en", {"s.p2": "two", "s.p1": "one", "other": "x"})
    assert t.section("s") == ["one", "two"]
    with pytest.raises(LocaleError):
        t.section("none")


def test_number_formatting_per_locale() -> None:
    assert i18n.fmt_number(1234.5, 1, "en") == "1,234.5"
    assert i18n.fmt_number(1234.5, 1, "pt-BR") == "1.234,5"
    assert i18n.fmt_number(0.86, 2, "pt-BR") == "0,86"
    assert i18n.fmt_percent(0.36, 0, "pt-BR") == "36%"
    assert i18n.fmt_percent(0.9897, 1, "en") == "99.0%"
