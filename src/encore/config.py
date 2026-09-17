"""Loader for the band list in config/bands.yaml.

Per docs/context/tech.md, the band list is versioned config, not code —
ingestion reads bands only from this file (spec-01 R2.2).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_BANDS_FILE = Path(__file__).resolve().parents[2] / "config" / "bands.yaml"


@dataclass(frozen=True)
class Band:
    name: str
    mbid: str


def load_bands(path: Path | None = None) -> list[Band]:
    """Load the band list from `path` (defaults to config/bands.yaml)."""
    file_path = path or DEFAULT_BANDS_FILE
    with file_path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)

    return [Band(name=entry["name"], mbid=entry["mbid"]) for entry in data["bands"]]
