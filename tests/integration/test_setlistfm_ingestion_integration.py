"""Integration coverage for encore.ingestion.setlistfm against a real
PostgreSQL (spec-01 R4/R6.6). Proves two things the mocked unit tests
in tests/test_ingestion_setlistfm.py can't: the upsert SQL actually
runs, and the exact TRUNCATE statement cleanup_raw_setlistfm uses
really empties every table — the ephemeral-data policy end to end.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from encore.config import Band
from encore.ingestion import setlistfm as sf

BAND = Band(name="Muse", mbid="9c9f1380-2516-4fc9-a3e6-f9f61941d090")


@pytest.fixture()
def clean_setlistfm_tables(pg_connection):
    sf.ensure_tables(pg_connection)
    sf.truncate_all(pg_connection)
    return pg_connection


def _mock_client():
    client = MagicMock()
    client.get_artist_setlists.return_value = {
        "setlist": [
            {
                "id": "sl-1",
                "eventDate": "18-06-2001",
                "tour": {"name": "Origin of Symmetry Tour"},
                "venue": {"name": "Some Venue", "city": {"name": "Paris", "country": {"name": "France"}}},
                "url": "https://www.setlist.fm/setlist/sl-1.html",
                "sets": {
                    "set": [
                        {
                            "song": [
                                {"name": "New Born"},
                                {"name": "Feeling Good", "cover": {"name": "Nina Simone"}},
                            ]
                        }
                    ]
                },
            }
        ],
        "itemsPerPage": 20,
    }
    return client


def test_extract_band_upserts_without_duplicating_on_a_second_run(clean_setlistfm_tables):
    conn = clean_setlistfm_tables
    client = _mock_client()

    sf.extract_band(client, conn, BAND, run_id="run-A")
    sf.extract_band(client, conn, BAND, run_id="run-B")

    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM raw_setlistfm.setlists")
        assert cur.fetchone()[0] == 1
        cur.execute("SELECT count(*) FROM raw_setlistfm.setlist_entries")
        assert cur.fetchone()[0] == 2
        cur.execute("SELECT run_id FROM raw_setlistfm.setlists WHERE setlist_id = 'sl-1'")
        assert cur.fetchone()[0] == "run-B"


def test_truncate_all_matches_what_cleanup_raw_setlistfm_runs(clean_setlistfm_tables):
    conn = clean_setlistfm_tables
    client = _mock_client()
    sf.extract_band(client, conn, BAND, run_id="run-A")

    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM raw_setlistfm.setlists")
        assert cur.fetchone()[0] == 1  # sanity: something was loaded

    sf.truncate_all(conn)

    with conn.cursor() as cur:
        for table in sf.TABLES:
            cur.execute(f"SELECT count(*) FROM raw_setlistfm.{table}")
            assert cur.fetchone()[0] == 0, f"{table} not empty after truncate_all"


def test_validate_bands_raises_on_zero_setlists(clean_setlistfm_tables):
    conn = clean_setlistfm_tables  # nothing loaded

    with pytest.raises(ValueError, match="Muse"):
        sf.validate_bands(conn, [BAND])


def test_validate_bands_reports_counts_after_a_real_load(clean_setlistfm_tables):
    conn = clean_setlistfm_tables
    client = _mock_client()
    sf.extract_band(client, conn, BAND, run_id="run-A")

    results = sf.validate_bands(conn, [BAND])

    assert results == [
        {
            "band": "Muse",
            "total_setlists": 1,
            "setlists_with_songs": 1,
            "pct_with_songs": 100.0,
        }
    ]
