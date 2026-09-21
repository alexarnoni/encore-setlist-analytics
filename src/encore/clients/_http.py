"""Shared HTTP helpers: rate limiting, retry/backoff, request counters.

Used by both encore.clients.musicbrainz and encore.clients.setlistfm so
the 429/503 backoff and per-API real-request counters
(docs/context/tech.md) are implemented once instead of per client.
"""

from __future__ import annotations

import time

import requests

MAX_RETRIES = 3
RETRY_BACKOFF_MAX = 16  # seconds; cap of the exponential backoff (2^n)

_counters: dict[str, int] = {}


def get_counters() -> dict[str, int]:
    """Real (non-cached) request counts per API, since the last reset."""
    return dict(_counters)


def reset_counters() -> None:
    _counters.clear()


def request_with_retry(
    session: requests.Session,
    url: str,
    *,
    params: dict | None = None,
    rate_delay: float,
    api_name: str,
) -> dict:
    """
    GET with exponential backoff on HTTP 429/503 (2s, 4s, 8s, capped at
    RETRY_BACKOFF_MAX), up to MAX_RETRIES attempts total (tech.md).

    Increments the real-request counter for `api_name` on every attempt —
    callers must only reach this function for calls that are not served
    from a local cache. Waits `rate_delay` seconds after a successful
    response, respecting the API's own rate limit.
    """
    attempt = 0
    last_status: int | None = None

    while attempt < MAX_RETRIES:
        _counters[api_name] = _counters.get(api_name, 0) + 1
        try:
            response = session.get(url, params=params, timeout=15)
            last_status = response.status_code

            if response.status_code in (429, 503):
                wait = min(2 ** (attempt + 1), RETRY_BACKOFF_MAX)
                time.sleep(wait)
                attempt += 1
                continue

            response.raise_for_status()
            time.sleep(rate_delay)
            return response.json()

        except requests.exceptions.RequestException:
            wait = min(2 ** (attempt + 1), RETRY_BACKOFF_MAX)
            time.sleep(wait)
            attempt += 1

    raise RuntimeError(
        f"[{api_name}] Failed after {MAX_RETRIES} attempts for: {url} "
        f"(last HTTP status: {last_status})"
    )
