"""Database helpers for the spec-03 synthetic data (disposable database only)."""

from __future__ import annotations

import os
import re
from collections import defaultdict

from psycopg2.extras import execute_values

from encore.config import load_bands
from tests.support.histories import SongPool, SyntheticShow
from tests.support.oracle import CatalogInfo

# Names that reach the catalog untouched: no " / " (medley separator), no
# brackets, no exotic punctuation. The typographic apostrophe is common in
# MusicBrainz titles.
_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ,.!?'’&-]{2,60}$")


def assert_spec03_database() -> None:
    """Refuse to run against anything but the isolated spec-03 Postgres.

    Inside the helper containers the host is `spec03-postgres`; from the host
    it is localhost:5446. The real database is reached as `postgres` or via
    localhost:5435, so those are refused.
    """
    host = os.environ.get("POSTGRES_HOST", "")
    port = os.environ.get("POSTGRES_PORT", "5432")
    inside = host == "spec03-postgres"
    outside = host in ("localhost", "127.0.0.1") and port == "5446"
    if not (inside or outside):
        raise RuntimeError(
            f"refusing to touch POSTGRES_HOST={host!r} POSTGRES_PORT={port!r}: "
            "spec-03 tools only run against spec03-postgres (source scripts/spec03/env.sh)"
        )


def load_pools(conn) -> tuple[dict[str, SongPool], dict[str, dict[str, CatalogInfo]]]:
    """Song pools per band and the catalog facts for every pooled name, read
    from intermediate.int_song_catalog (built from the MusicBrainz copy)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            select band, song_title, catalog_source, reference_album, release_year
            from intermediate.int_song_catalog
            order by band, title_normalized
            """
        )
        rows = cur.fetchall()
    album: dict[str, list[str]] = defaultdict(list)
    with_year: dict[str, list[str]] = defaultdict(list)
    no_year: dict[str, list[str]] = defaultdict(list)
    catalog: dict[str, dict[str, CatalogInfo]] = defaultdict(dict)
    for band, title, source, reference_album, release_year in rows:
        if not _SAFE_NAME.match(title) or title in catalog[band]:
            continue
        catalog[band][title] = CatalogInfo(reference_album, release_year)
        if source in ("album", "override"):
            album[band].append(title)
        elif release_year is not None:
            with_year[band].append(title)
        else:
            no_year[band].append(title)
    pools = {band: SongPool(tuple(album[band]), tuple(with_year[band]), tuple(no_year[band]))
             for band in catalog}
    return pools, dict(catalog)


def reset_raw_setlistfm(conn) -> None:
    assert_spec03_database()
    with conn.cursor() as cur:
        cur.execute("truncate raw_setlistfm.setlist_entries, raw_setlistfm.setlists, raw_setlistfm.raw_responses")
    conn.commit()


def insert_histories(conn, shows: list[SyntheticShow]) -> tuple[int, int]:
    """Insert the shows through the same raw tables the real ingestion fills."""
    assert_spec03_database()
    mbid = {band.name: band.mbid for band in load_bands()}
    setlists, entries = [], []
    for s in shows:
        setlists.append((
            s.setlist_id, mbid[s.band], s.band,
            s.show_date.strftime("%d-%m-%Y") if s.show_date else None,
            s.tour_name, "Synthetic Venue", "Nowhere", "XX",
            f"https://example.invalid/{s.setlist_id}", "synthetic",
        ))
        pos = 0

        def add(name: str, *, cover: bool = False, tape: bool = False) -> None:
            nonlocal pos
            pos += 1
            entries.append((s.setlist_id, 0, pos, name, False, cover,
                            "Synthetic Artist" if cover else None, tape, "synthetic"))

        for name in (*s.songs, *s.unmatched):
            add(name)
        for name in s.covers:
            add(name, cover=True)
        for name in s.tape:
            add(name, tape=True)
    with conn.cursor() as cur:
        execute_values(
            cur,
            "insert into raw_setlistfm.setlists (setlist_id, artist_mbid, band_name, event_date, "
            "tour_name, venue_name, city, country, setlistfm_url, run_id) values %s",
            setlists,
        )
        execute_values(
            cur,
            "insert into raw_setlistfm.setlist_entries (setlist_id, set_idx, position, song_name, "
            "is_encore, is_cover, cover_artist, is_tape, run_id) values %s",
            entries,
        )
    conn.commit()
    return len(setlists), len(entries)
