"""setlist.fm extraction into the ephemeral raw_setlistfm schema (spec-01 R4).

Every request goes straight through
encore.clients.setlistfm.SetlistFmClient (no disk cache — R3.2) into
`raw_setlistfm`, which is truncated at the end of every run (data
policy, docs/context/product.md). Raw JSON is stored only when
explicitly enabled (R4.3), since it exists purely for debugging.
"""

from __future__ import annotations

import json
import os

from encore.clients._http import get_counters

# Safety margin below setlist.fm's 1,440 requests/day limit (R4.4). This
# is a hard stop inside a single extraction run; the smarter pre-run
# estimate (today's logged requests + last run's cost) lives in the
# Airflow check_api_budget task, not here.
MAX_REQUESTS_PER_RUN = 1300

STORE_RAW_JSON_ENV_VAR = "ENCORE_STORE_RAW_SETLISTFM_JSON"


def ensure_tables(conn) -> None:
    """Create the raw_setlistfm tables if they don't exist yet (idempotent)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS raw_setlistfm.setlists (
                setlist_id TEXT PRIMARY KEY,
                artist_mbid TEXT NOT NULL,
                band_name TEXT NOT NULL,
                event_date TEXT,
                tour_name TEXT,
                venue_name TEXT,
                city TEXT,
                country TEXT,
                setlistfm_url TEXT,
                run_id TEXT NOT NULL,
                loaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS raw_setlistfm.setlist_entries (
                setlist_id TEXT NOT NULL
                    REFERENCES raw_setlistfm.setlists (setlist_id),
                set_idx INTEGER NOT NULL,
                position INTEGER NOT NULL,
                song_name TEXT NOT NULL,
                is_encore BOOLEAN NOT NULL,
                is_cover BOOLEAN NOT NULL,
                cover_artist TEXT,
                is_tape BOOLEAN NOT NULL,
                run_id TEXT NOT NULL,
                PRIMARY KEY (setlist_id, set_idx, position)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS raw_setlistfm.raw_responses (
                setlist_id TEXT PRIMARY KEY,
                payload JSONB NOT NULL,
                run_id TEXT NOT NULL,
                loaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
    conn.commit()


def fetch_all_setlists(client, mbid: str) -> list[dict]:
    """
    Paginate /artist/{mbid}/setlists to the last page (R4.1).

    Stops when a page returns fewer items than `itemsPerPage`, or when
    the real-request counter would exceed MAX_REQUESTS_PER_RUN (R4.4) —
    raises RuntimeError in that case so the caller aborts the run instead
    of silently returning a partial result.
    """
    setlists: list[dict] = []
    page = 1
    while True:
        if get_counters().get("setlistfm", 0) >= MAX_REQUESTS_PER_RUN:
            raise RuntimeError(
                f"setlist.fm request budget of {MAX_REQUESTS_PER_RUN} reached "
                f"while fetching setlists for artist {mbid}; aborting run."
            )

        response = client.get_artist_setlists(mbid=mbid, page=page)
        page_items = response.get("setlist", [])
        setlists.extend(page_items)

        items_per_page = response.get("itemsPerPage", 20)
        if len(page_items) < items_per_page:
            break
        page += 1

    return setlists


def _parse_song(set_idx: int, position: int, song: dict, is_encore: bool) -> dict:
    cover = song.get("cover")
    return {
        "set_idx": set_idx,
        "position": position,
        "song_name": song.get("name", ""),
        "is_encore": is_encore,
        "is_cover": cover is not None,
        "cover_artist": cover.get("name") if cover else None,
        "is_tape": bool(song.get("tape", False)),
    }


def parse_setlist(setlist: dict) -> tuple[dict, list[dict]]:
    """
    Split one raw setlist.fm setlist object into a `setlists` row and its
    `setlist_entries` rows.

    A "set" block counts as an encore (is_encore=True) when the API
    marks it with an "encore" field, matching setlist.fm's own
    convention for encore sets.
    """
    venue = setlist.get("venue", {}) or {}
    city = venue.get("city", {}) or {}
    country = city.get("country", {}) or {}
    tour = setlist.get("tour", {}) or {}

    setlist_row = {
        "setlist_id": setlist["id"],
        "event_date": setlist.get("eventDate"),
        "tour_name": tour.get("name"),
        "venue_name": venue.get("name"),
        "city": city.get("name"),
        "country": country.get("name"),
        "setlistfm_url": setlist.get("url"),
    }

    entries: list[dict] = []
    sets = (setlist.get("sets", {}) or {}).get("set", [])
    for set_idx, set_block in enumerate(sets):
        is_encore = "encore" in set_block
        for position, song in enumerate(set_block.get("song", []), start=1):
            entries.append(_parse_song(set_idx, position, song, is_encore))

    return setlist_row, entries


def _upsert_setlist(cur, band, run_id: str, setlist_row: dict) -> None:
    cur.execute(
        """
        INSERT INTO raw_setlistfm.setlists
            (setlist_id, artist_mbid, band_name, event_date, tour_name,
             venue_name, city, country, setlistfm_url, run_id, loaded_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
        ON CONFLICT (setlist_id) DO UPDATE SET
            event_date = EXCLUDED.event_date,
            tour_name = EXCLUDED.tour_name,
            venue_name = EXCLUDED.venue_name,
            city = EXCLUDED.city,
            country = EXCLUDED.country,
            setlistfm_url = EXCLUDED.setlistfm_url,
            run_id = EXCLUDED.run_id,
            loaded_at = now()
        """,
        (
            setlist_row["setlist_id"],
            band.mbid,
            band.name,
            setlist_row["event_date"],
            setlist_row["tour_name"],
            setlist_row["venue_name"],
            setlist_row["city"],
            setlist_row["country"],
            setlist_row["setlistfm_url"],
            run_id,
        ),
    )


def _insert_entry(cur, setlist_id: str, run_id: str, entry: dict) -> None:
    cur.execute(
        """
        INSERT INTO raw_setlistfm.setlist_entries
            (setlist_id, set_idx, position, song_name, is_encore, is_cover,
             cover_artist, is_tape, run_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (setlist_id, set_idx, position) DO UPDATE SET
            song_name = EXCLUDED.song_name,
            is_encore = EXCLUDED.is_encore,
            is_cover = EXCLUDED.is_cover,
            cover_artist = EXCLUDED.cover_artist,
            is_tape = EXCLUDED.is_tape,
            run_id = EXCLUDED.run_id
        """,
        (
            setlist_id,
            entry["set_idx"],
            entry["position"],
            entry["song_name"],
            entry["is_encore"],
            entry["is_cover"],
            entry["cover_artist"],
            entry["is_tape"],
            run_id,
        ),
    )


def _store_raw_json(cur, setlist: dict, run_id: str) -> None:
    cur.execute(
        """
        INSERT INTO raw_setlistfm.raw_responses (setlist_id, payload, run_id, loaded_at)
        VALUES (%s, %s, %s, now())
        ON CONFLICT (setlist_id) DO UPDATE SET
            payload = EXCLUDED.payload,
            run_id = EXCLUDED.run_id,
            loaded_at = now()
        """,
        (setlist["id"], json.dumps(setlist), run_id),
    )


def extract_band(client, conn, band, run_id: str) -> dict:
    """
    Extract every setlist of one band into raw_setlistfm (R4).

    Raw JSON is only persisted (R4.3) when `ENCORE_STORE_RAW_SETLISTFM_JSON`
    is set to a truthy value ("1", "true", "yes") — it exists purely for
    debugging and gets truncated with everything else in raw_setlistfm at
    the end of the run.
    """
    store_raw_json = os.environ.get(STORE_RAW_JSON_ENV_VAR, "").lower() in ("1", "true", "yes")

    setlists = fetch_all_setlists(client, band.mbid)
    entries_loaded = 0

    with conn.cursor() as cur:
        for setlist in setlists:
            setlist_row, entries = parse_setlist(setlist)
            _upsert_setlist(cur, band, run_id, setlist_row)
            for entry in entries:
                _insert_entry(cur, setlist_row["setlist_id"], run_id, entry)
                entries_loaded += 1
            if store_raw_json:
                _store_raw_json(cur, setlist, run_id)

    conn.commit()

    return {"band": band.name, "setlists": len(setlists), "entries": entries_loaded}
