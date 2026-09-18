"""Loader for the band list in config/bands.yaml.

Per docs/context/tech.md, the band list is versioned config, not code —
ingestion reads bands only from this file (spec-01 R2.2).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

# Assumes the repo layout (config/ next to src/) — true for local dev and
# for the notebook, but not inside the Airflow image, where config/ is
# copied to a different path to avoid colliding with Airflow's own
# /opt/airflow/config directory. ENCORE_BANDS_FILE overrides this for
# any environment where the assumption doesn't hold (see airflow/Dockerfile).
DEFAULT_BANDS_FILE = Path(__file__).resolve().parents[2] / "config" / "bands.yaml"


@dataclass(frozen=True)
class Band:
    name: str
    mbid: str


def load_bands(path: Path | None = None) -> list[Band]:
    """
    Load the band list from `path`, or ENCORE_BANDS_FILE if set,
    defaulting to config/bands.yaml relative to the repo layout.
    """
    file_path = path or Path(os.environ.get("ENCORE_BANDS_FILE", DEFAULT_BANDS_FILE))
    with file_path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)

    return [Band(name=entry["name"], mbid=entry["mbid"]) for entry in data["bands"]]
