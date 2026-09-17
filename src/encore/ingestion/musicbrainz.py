"""Pure selection logic for MusicBrainz release data.

No network or database access lives here; this module only transforms
data already fetched by src/encore/clients/musicbrainz.py.
"""

from __future__ import annotations

from collections import Counter

# Country preference when releases are still tied after track count and date.
_COUNTRY_RANK = {"GB": 0, "US": 1, "XW": 2}
_UNKNOWN_COUNTRY_RANK = 3


def _track_count(release: dict) -> int:
    """Total track count of a release, summed across all its media."""
    return sum(medium.get("track-count", 0) for medium in release.get("media", []))


def _date_sort_key(release: dict) -> tuple[int, int, int]:
    """
    Sortable key for a release's date, earliest first.

    MusicBrainz dates may be missing or have partial precision ("YYYY",
    "YYYY-MM", "YYYY-MM-DD"). Missing parts are treated as the start of the
    period (month 1, day 1) so a bare year sorts as 1 January of that year.
    A missing date sorts last (as if it were far in the future).
    """
    date_str = release.get("date")
    if not date_str:
        return (9999, 12, 31)

    parts = date_str.split("-")
    year = int(parts[0])
    month = int(parts[1]) if len(parts) > 1 and parts[1] else 1
    day = int(parts[2]) if len(parts) > 2 and parts[2] else 1
    return (year, month, day)


def _country_rank(release: dict) -> int:
    return _COUNTRY_RANK.get(release.get("country"), _UNKNOWN_COUNTRY_RANK)


def select_representative_release(releases: list[dict]) -> dict | None:
    """
    Pick the representative release of a release-group.

    Selection order:
    1. Mode of track count across the official releases (the count shared by
       the most releases). If several counts are equally frequent, all
       releases with any of those counts remain in contention.
    2. Among the remaining releases, the earliest date wins.
    3. Remaining ties are broken by country preference: GB > US > XW >
       anything else (including missing country).

    Returns None if `releases` is empty.
    """
    if not releases:
        return None

    counts = [_track_count(release) for release in releases]
    frequency = Counter(counts)
    max_frequency = max(frequency.values())
    modal_counts = {count for count, freq in frequency.items() if freq == max_frequency}

    candidates = [release for release in releases if _track_count(release) in modal_counts]

    return min(candidates, key=lambda release: (_date_sort_key(release), _country_rank(release)))
