"""The bands in scope: names and order from `config/bands.yaml`, URL slugs, colours."""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).resolve().parents[3] / "config" / "bands.yaml"


@lru_cache(maxsize=None)
def band_names(path: Path = CONFIG_PATH) -> tuple[str, ...]:
    """Band names in config order (the order that fixes each band's colour)."""
    data = yaml.safe_load(path.read_text(encoding="utf8"))
    return tuple(b["name"] for b in data["bands"])


def slug(name: str) -> str:
    """URL slug of a band: lowercase ASCII words joined by hyphens."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")


def key(name: str) -> str:
    """Identifier-safe form of a band name, used in placeholder names (`twenty_one_pilots`)."""
    return slug(name).replace("-", "_")
