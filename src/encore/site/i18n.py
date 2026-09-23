"""Locale files, strict lookups and locale-aware number formatting.

All user-facing strings live in `locales/<locale>.yml` (nested YAML, flattened
to dotted keys). The build fails, rather than shipping a gap, when:

- a key exists in one locale and not the other (`validate_parity`);
- a template asks for a key that does not exist (`Translator.__call__`);
- a string uses a `{{ placeholder }}` for which no value was supplied (R4).

Strings may contain `{{ placeholders }}` and a little trusted inline HTML. Values
substituted into them are HTML-escaped; the literal text of the locale file is not.
Band, album and tour names never come from here: they are data.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

import yaml
from jinja2 import Environment, StrictUndefined, TemplateSyntaxError, UndefinedError, meta
from markupsafe import Markup

LOCALES: tuple[str, ...] = ("pt-BR", "en")
DEFAULT_LOCALE = "pt-BR"
# Output directory of each locale under `site/`.
URL_PREFIX: dict[str, str] = {"pt-BR": "pt", "en": "en"}
LOCALES_DIR = Path(__file__).parent / "locales"


class LocaleError(Exception):
    """A locale file problem that must stop the build."""


def flatten(data: dict[str, Any], prefix: str = "") -> dict[str, str]:
    """Flatten nested mappings to dotted keys; leaves must be strings."""
    flat: dict[str, str] = {}
    for key, value in data.items():
        full = f"{prefix}{key}"
        if isinstance(value, dict):
            flat.update(flatten(value, f"{full}."))
        elif isinstance(value, str):
            flat[full] = value
        else:
            raise LocaleError(f"{full}: locale values must be strings, got {type(value).__name__}")
    return flat


def load_locales(directory: Path = LOCALES_DIR, locales: tuple[str, ...] = LOCALES) -> dict[str, dict[str, str]]:
    """Load every locale file, flattened, and check that they define the same keys."""
    loaded: dict[str, dict[str, str]] = {}
    for locale in locales:
        path = directory / f"{locale}.yml"
        if not path.exists():
            raise LocaleError(f"missing locale file: {path}")
        loaded[locale] = flatten(yaml.safe_load(path.read_text(encoding="utf8")) or {})
    validate_parity(loaded)
    return loaded


def validate_parity(loaded: dict[str, dict[str, str]]) -> None:
    """Raise if any locale lacks a key another locale has."""
    all_keys = set().union(*(set(v) for v in loaded.values()))
    problems = [
        f"{locale}: missing {sorted(all_keys - set(strings))}"
        for locale, strings in loaded.items()
        if all_keys - set(strings)
    ]
    if problems:
        raise LocaleError("locale key mismatch: " + "; ".join(problems))


def fmt_number(value: float, decimals: int, locale: str) -> str:
    """Format a number with the locale's separators (pt-BR `1.234,5`, en `1,234.5`)."""
    text = f"{value:,.{decimals}f}"
    if locale == "pt-BR":
        text = text.replace(",", "\0").replace(".", ",").replace("\0", ".")
    return text


def fmt_percent(fraction: float, decimals: int, locale: str) -> str:
    """Format a 0-1 fraction as a percentage string (no space before the sign)."""
    return fmt_number(fraction * 100, decimals, locale) + "%"


def _environment() -> Environment:
    return Environment(undefined=StrictUndefined, autoescape=True)


@lru_cache(maxsize=None)
def _compile(text: str):
    return _environment().from_string(text)


class Translator:
    """Strict string lookup for one locale, with placeholder values bound in."""

    def __init__(self, locale: str, strings: dict[str, str], values: dict[str, Any] | None = None,
                 fill_missing: Callable[[str], str | None] | None = None) -> None:
        self.locale = locale
        self.strings = strings
        self.values = dict(values or {})
        # Test hook only: `fill_missing(name)` gives a stand-in for a placeholder that has no value
        # (or None to leave it missing), so fake marts can render text written for the real data.
        # The shipped build never sets it.
        self.fill_missing = fill_missing

    def __call__(self, key: str, **extra: Any) -> Markup:
        """Return the string for `key`, placeholders filled; raise if a key or value is missing."""
        try:
            text = self.strings[key]
        except KeyError:
            raise LocaleError(f"[{self.locale}] missing translation key: {key}") from None
        context = {**self.values, **extra}
        if self.fill_missing is not None:
            for name in meta.find_undeclared_variables(_environment().parse(text)):
                stand_in = None if name in context else self.fill_missing(name)
                if stand_in is not None:
                    context[name] = stand_in
        try:
            return Markup(_compile(text).render(**context))
        except UndefinedError as exc:
            raise LocaleError(f"[{self.locale}] {key}: unfilled placeholder ({exc.message})") from None
        except TemplateSyntaxError as exc:
            raise LocaleError(f"[{self.locale}] {key}: bad placeholder syntax ({exc.message})") from None

    def value(self, name: str) -> str:
        """The formatted figure behind a placeholder, for templates that print it outside a string."""
        if name in self.values:
            return self.values[name]
        stand_in = self.fill_missing(name) if self.fill_missing is not None else None
        if stand_in is None:
            raise LocaleError(f"[{self.locale}] no value for placeholder: {name}")
        return stand_in

    def plain(self, key: str, **extra: Any) -> str:
        """Like `__call__` but a plain `str`, for chart labels and other non-HTML contexts."""
        return str(self(key, **extra))

    def section(self, prefix: str, **extra: Any) -> list[Markup]:
        """Return every string under `prefix.` in key order (for paragraphs `p1`, `p2`, ...)."""
        keys = sorted(k for k in self.strings if k.startswith(f"{prefix}."))
        if not keys:
            raise LocaleError(f"[{self.locale}] no keys under: {prefix}")
        return [self(k, **extra) for k in keys]

    def number(self, value: float, decimals: int = 0) -> str:
        """Format a number for this locale."""
        return fmt_number(value, decimals, self.locale)

    def percent(self, fraction: float, decimals: int = 0) -> str:
        """Format a fraction as a percentage for this locale."""
        return fmt_percent(fraction, decimals, self.locale)
