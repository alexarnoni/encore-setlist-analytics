"""MusicBrainz API client (spec-01 R3, R5).

Disk cache is intentionally kept for this client (R3.3): MusicBrainz
discography data is persistent and comparatively expensive to refetch
every run, unlike setlist.fm's ephemeral setlists — see
encore.clients.setlistfm, which drops the cache entirely.
"""

from __future__ import annotations

import json
from pathlib import Path

import requests

from ._http import request_with_retry

USER_AGENT = "Encore/0.1 (alexandre.anf@gmail.com)"
RATE_DELAY = 1.0  # MusicBrainz allows at most 1 request/second (tech.md)
CACHE_DIR = Path(__file__).resolve().parents[3] / "data" / "raw" / "musicbrainz"


def _cache_path(cache_key: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{cache_key}.json"


def _load_cache(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        # Corrupted cache file: discard it and let the caller re-fetch.
        return None


def _save_cache(path: Path, data: dict) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


class MusicBrainzClient:
    """Client for the MusicBrainz API, with a disk cache (R3.3)."""

    BASE_URL = "https://musicbrainz.org/ws/2"

    def __init__(self) -> None:
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": USER_AGENT})

    def _get(
        self,
        endpoint: str,
        params: dict | None = None,
        *,
        cache_key: str,
    ) -> dict:
        cache_file = _cache_path(cache_key)
        cached = _load_cache(cache_file)
        if cached is not None:
            return cached

        base_params = {"fmt": "json"}
        if params:
            base_params.update(params)

        data = request_with_retry(
            self._session,
            f"{self.BASE_URL}/{endpoint}",
            params=base_params,
            rate_delay=RATE_DELAY,
            api_name="musicbrainz",
        )
        _save_cache(cache_file, data)
        return data

    def search_artist(self, artist_name: str) -> dict:
        """Search artists by name, ranked by score (0-100) descending."""
        safe_name = "".join(c if c.isalnum() else "_" for c in artist_name).lower()
        return self._get(
            "artist",
            {"query": artist_name, "limit": 5},
            cache_key=f"search_artist_{safe_name}",
        )

    def get_artist(self, mbid: str) -> dict:
        """Artist details (name, country, life-span, aliases) by MBID."""
        return self._get(
            f"artist/{mbid}",
            {"inc": "aliases"},
            cache_key=f"artist_{mbid}",
        )

    def get_release_groups(self, mbid: str, offset: int = 0) -> dict:
        """Studio-album release-groups of an artist, paginated."""
        return self._get(
            f"artist/{mbid}",
            {"inc": "release-groups", "type": "album", "limit": 100, "offset": offset},
            cache_key=f"artist_{mbid}_release_groups_off{offset}",
        )

    def get_release_group_detail(self, rg_mbid: str) -> dict:
        """Release-group details, including its releases' dates."""
        return self._get(
            f"release-group/{rg_mbid}",
            {"inc": "releases"},
            cache_key=f"release_group_{rg_mbid}",
        )

    def get_releases_for_release_group(self, rg_mbid: str) -> dict:
        """
        Official releases of a release-group, with their tracks
        (recording id and title), used to pick the representative
        release (see encore.ingestion.musicbrainz).
        """
        return self._get(
            "release",
            {
                "release-group": rg_mbid,
                "status": "official",
                "inc": "recordings",
                "limit": 100,
            },
            cache_key=f"releases_rg_{rg_mbid}",
        )

    def get_recordings(self, mbid: str, offset: int = 0) -> dict:
        """
        All recordings of an artist, paginated 100 at a time. Each
        recording's "first-release-date" is a string with variable
        precision ("YYYY", "YYYY-MM" or "YYYY-MM-DD").
        """
        return self._get(
            "recording",
            {"artist": mbid, "limit": 100, "offset": offset},
            cache_key=f"recordings_artist_{mbid}_off{offset}",
        )
