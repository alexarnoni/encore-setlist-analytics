"""Integration coverage for encore.ingestion.musicbrainz against a real
PostgreSQL (spec-01 R5.5/R5.6). The unit tests in
tests/test_ingestion_musicbrainz.py mock the DB entirely; this proves
the actual SQL (upsert syntax, FK, the skip query) runs correctly.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from encore.config import Band
from encore.ingestion import musicbrainz as mb

BAND = Band(name="Muse", mbid="9c9f1380-2516-4fc9-a3e6-f9f61941d090")


@pytest.fixture()
def clean_musicbrainz_tables(pg_connection):
    mb.ensure_tables(pg_connection)
    with pg_connection.cursor() as cur:
        cur.execute(
            "TRUNCATE raw_musicbrainz.album_tracks, raw_musicbrainz.albums, "
            "raw_musicbrainz.recordings"
        )
    pg_connection.commit()
    return pg_connection


def _mock_client():
    client = MagicMock()
    client.get_release_groups.return_value = {
        "release-groups": [{"id": "rg1", "title": "Origin of Symmetry", "primary-type": "Album"}]
    }
    client.get_releases_for_release_group.return_value = {
        "releases": [
            {
                "date": "2001-06-18",
                "country": "GB",
                "media": [
                    {
                        "track-count": 2,
                        "tracks": [
                            {"recording": {"id": "rec1", "title": "New Born"}},
                            {"recording": {"id": "rec2", "title": "Bliss"}},
                        ],
                    }
                ],
            }
        ]
    }
    client.get_recordings.return_value = {
        "recordings": [{"id": "rec1", "title": "New Born", "first-release-date": "2001-06-18"}],
        "recording-count": 1,
    }
    return client


def test_extract_band_upserts_without_duplicating_on_a_second_run(clean_musicbrainz_tables):
    conn = clean_musicbrainz_tables
    client = _mock_client()

    mb.extract_band(client, conn, BAND, refresh_after_days=0)
    mb.extract_band(client, conn, BAND, refresh_after_days=0)

    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM raw_musicbrainz.albums")
        assert cur.fetchone()[0] == 1
        cur.execute("SELECT count(*) FROM raw_musicbrainz.album_tracks")
        assert cur.fetchone()[0] == 2
        cur.execute("SELECT count(*) FROM raw_musicbrainz.recordings")
        assert cur.fetchone()[0] == 1


def test_extract_band_skips_when_data_is_fresh(clean_musicbrainz_tables):
    conn = clean_musicbrainz_tables
    client = _mock_client()

    mb.extract_band(client, conn, BAND)  # default 30-day threshold
    summary = mb.extract_band(client, conn, BAND)  # should skip

    assert summary["skipped"] is True
    client.get_release_groups.assert_called_once()  # only the first call
