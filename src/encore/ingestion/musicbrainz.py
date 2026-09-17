"""MusicBrainz extraction into raw_musicbrainz (spec-01 R5).

`select_representative_release` and its helpers are pure functions with
no I/O. `ensure_tables`/`extract_band` do the actual extraction: they
take an already-constructed encore.clients.musicbrainz.MusicBrainzClient
and an open DB connection (see encore.db.get_connection), so they stay
testable with mocks instead of needing a live client or database.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone

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


# ---------------------------------------------------------------------------
# Extraction into raw_musicbrainz
# ---------------------------------------------------------------------------

PAGE_SIZE = 100
# Guards against an infinite pagination loop if the API ever misbehaves.
# 500 pages mirrors R5.2's explicit guard for the recordings endpoint;
# release-groups never come close to needing that many pages per band,
# but the same safety net is cheap to apply.
MAX_RELEASE_GROUP_PAGES = 500
MAX_RECORDING_PAGES = 500

DEFAULT_REFRESH_DAYS = 30


def ensure_tables(conn) -> None:
    """Create the raw_musicbrainz tables if they don't exist yet (idempotent)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS raw_musicbrainz.albums (
                release_group_mbid TEXT PRIMARY KEY,
                band_mbid TEXT NOT NULL,
                band_name TEXT NOT NULL,
                title TEXT NOT NULL,
                first_release_date TEXT,
                loaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS raw_musicbrainz.album_tracks (
                release_group_mbid TEXT NOT NULL
                    REFERENCES raw_musicbrainz.albums (release_group_mbid),
                recording_mbid TEXT NOT NULL,
                title TEXT NOT NULL,
                track_position INTEGER NOT NULL,
                loaded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                PRIMARY KEY (release_group_mbid, recording_mbid)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS raw_musicbrainz.recordings (
                recording_mbid TEXT PRIMARY KEY,
                band_mbid TEXT NOT NULL,
                band_name TEXT NOT NULL,
                title TEXT NOT NULL,
                first_release_date TEXT,
                loaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
    conn.commit()


def _is_studio_album(release_group: dict) -> bool:
    """Primary-type Album, no secondary types (R5.1) — e.g. excludes
    live albums, compilations, soundtracks classified as secondary types
    of an otherwise-Album release-group."""
    secondary_types = release_group.get("secondary-types") or []
    return release_group.get("primary-type") == "Album" and not secondary_types


def fetch_studio_albums(client, mbid: str) -> list[dict]:
    """Paginate an artist's release-groups, keep primary studio albums only."""
    albums: list[dict] = []
    offset = 0
    for _ in range(MAX_RELEASE_GROUP_PAGES):
        page = client.get_release_groups(mbid, offset=offset).get("release-groups", [])
        albums.extend(rg for rg in page if _is_studio_album(rg))
        if len(page) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    return albums


def fetch_all_recordings(client, mbid: str) -> list[dict]:
    """Paginate every recording of an artist (R5.2 explicit 500-page guard)."""
    recordings: list[dict] = []
    offset = 0
    for _ in range(MAX_RECORDING_PAGES):
        response = client.get_recordings(mbid, offset=offset)
        page = response.get("recordings", [])
        if not page:
            break
        recordings.extend(page)
        total = response.get("recording-count", 0)
        offset += len(page)
        if offset >= total:
            break
    return recordings


def _album_tracks_from_release(release: dict) -> list[tuple[str, str]]:
    """(recording_mbid, title) pairs from a release's media, in order."""
    tracks: list[tuple[str, str]] = []
    for medium in release.get("media", []):
        for track in medium.get("tracks", []):
            recording = track.get("recording", {})
            recording_mbid = recording.get("id")
            title = recording.get("title") or track.get("title")
            if recording_mbid and title:
                tracks.append((recording_mbid, title))
    return tracks


def should_skip_band(conn, band_mbid: str, refresh_after_days: int = DEFAULT_REFRESH_DAYS) -> bool:
    """
    True if raw_musicbrainz already has data for this band newer than
    `refresh_after_days` (R5.6) — skips a discography that rarely
    changes instead of re-fetching it on every run.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT max(loaded_at) FROM raw_musicbrainz.recordings WHERE band_mbid = %s",
            (band_mbid,),
        )
        (last_loaded,) = cur.fetchone()

    if last_loaded is None:
        return False
    return datetime.now(timezone.utc) - last_loaded < timedelta(days=refresh_after_days)


def _upsert_album(cur, band, album: dict) -> None:
    cur.execute(
        """
        INSERT INTO raw_musicbrainz.albums
            (release_group_mbid, band_mbid, band_name, title, first_release_date, loaded_at)
        VALUES (%s, %s, %s, %s, %s, now())
        ON CONFLICT (release_group_mbid) DO UPDATE SET
            title = EXCLUDED.title,
            first_release_date = EXCLUDED.first_release_date,
            loaded_at = EXCLUDED.loaded_at
        """,
        (album["id"], band.mbid, band.name, album["title"], album.get("first-release-date")),
    )


def _upsert_album_track(
    cur, release_group_mbid: str, recording_mbid: str, title: str, position: int
) -> None:
    cur.execute(
        """
        INSERT INTO raw_musicbrainz.album_tracks
            (release_group_mbid, recording_mbid, title, track_position, loaded_at)
        VALUES (%s, %s, %s, %s, now())
        ON CONFLICT (release_group_mbid, recording_mbid) DO UPDATE SET
            title = EXCLUDED.title,
            track_position = EXCLUDED.track_position,
            loaded_at = EXCLUDED.loaded_at
        """,
        (release_group_mbid, recording_mbid, title, position),
    )


def _upsert_recording(cur, band, recording: dict) -> None:
    cur.execute(
        """
        INSERT INTO raw_musicbrainz.recordings
            (recording_mbid, band_mbid, band_name, title, first_release_date, loaded_at)
        VALUES (%s, %s, %s, %s, %s, now())
        ON CONFLICT (recording_mbid) DO UPDATE SET
            title = EXCLUDED.title,
            first_release_date = EXCLUDED.first_release_date,
            loaded_at = EXCLUDED.loaded_at
        """,
        (recording["id"], band.mbid, band.name, recording.get("title"), recording.get("first-release-date")),
    )


def extract_band(client, conn, band, *, refresh_after_days: int = DEFAULT_REFRESH_DAYS) -> dict:
    """
    Extract one band's studio albums (+ representative release tracks)
    and full recordings catalog into raw_musicbrainz (R5).

    Skips the whole band if data younger than `refresh_after_days`
    already exists (R5.6). Every write is an upsert, so calling this
    twice for the same band never creates duplicates (R5.5).

    `client` is an encore.clients.musicbrainz.MusicBrainzClient, `conn`
    an open connection from encore.db.get_connection(), `band` an
    encore.config.Band.
    """
    if should_skip_band(conn, band.mbid, refresh_after_days):
        return {"band": band.name, "skipped": True, "albums": 0, "tracks": 0, "recordings": 0}

    albums = fetch_studio_albums(client, band.mbid)
    tracks_loaded = 0

    with conn.cursor() as cur:
        for album in albums:
            _upsert_album(cur, band, album)

            releases = client.get_releases_for_release_group(album["id"]).get("releases", [])
            representative = select_representative_release(releases)
            if representative is None:
                continue

            for position, (recording_mbid, title) in enumerate(
                _album_tracks_from_release(representative), start=1
            ):
                _upsert_album_track(cur, album["id"], recording_mbid, title, position)
                tracks_loaded += 1

        recordings = fetch_all_recordings(client, band.mbid)
        for recording in recordings:
            _upsert_recording(cur, band, recording)

    conn.commit()

    return {
        "band": band.name,
        "skipped": False,
        "albums": len(albums),
        "tracks": tracks_loaded,
        "recordings": len(recordings),
    }
