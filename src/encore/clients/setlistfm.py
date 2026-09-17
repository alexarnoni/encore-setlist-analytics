"""setlist.fm API client (spec-01 R3, R4).

No disk cache here (R3.2): setlist.fm data is ephemeral by data policy
(docs/context/product.md) — responses go straight into raw_setlistfm and
are truncated at the end of every run, so caching them to disk would
defeat that policy. Compare with encore.clients.musicbrainz, which keeps
a cache because MusicBrainz data is meant to persist.
"""

from __future__ import annotations

import os

import requests

from ._http import request_with_retry

RATE_DELAY = 1.0  # setlist.fm allows 2 req/s; a 1s pause is a safe margin


class SetlistFmClient:
    """Client for the setlist.fm API. Every call hits the network."""

    BASE_URL = "https://api.setlist.fm/rest/1.0"

    def __init__(self) -> None:
        api_key = os.getenv("SETLISTFM_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "SETLISTFM_API_KEY not set. Create a .env file at the "
                "project root with this variable (see .env.example)."
            )
        self._session = requests.Session()
        self._session.headers.update(
            {
                "x-api-key": api_key,
                "Accept": "application/json",
            }
        )

    def get_artist_setlists(self, mbid: str, page: int = 1) -> dict:
        """Setlists of an artist by MBID, one page (20 items) at a time."""
        return request_with_retry(
            self._session,
            f"{self.BASE_URL}/artist/{mbid}/setlists",
            params={"p": page},
            rate_delay=RATE_DELAY,
            api_name="setlistfm",
        )

    def search_artist(self, artist_name: str) -> dict:
        """Search artists by name, sorted by relevance."""
        return request_with_retry(
            self._session,
            f"{self.BASE_URL}/search/artists",
            params={"artistName": artist_name, "sort": "relevance"},
            rate_delay=RATE_DELAY,
            api_name="setlistfm",
        )
