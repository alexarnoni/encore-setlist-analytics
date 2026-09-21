from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from encore.config import Band
from encore.ingestion.musicbrainz import (
    DEFAULT_REFRESH_DAYS,
    extract_band,
    fetch_all_recordings,
    fetch_studio_albums,
    should_skip_band,
)

BAND = Band(name="Muse", mbid="9c9f1380-2516-4fc9-a3e6-f9f61941d090")


def _cursor(conn) -> MagicMock:
    return conn.cursor.return_value.__enter__.return_value


# --- fetch_studio_albums --------------------------------------------------


def test_fetch_studio_albums_keeps_only_primary_albums_without_secondary_types():
    client = MagicMock()
    client.get_release_groups.return_value = {
        "release-groups": [
            {"id": "a1", "title": "Studio Album", "primary-type": "Album"},
            {"id": "a2", "title": "Live Album", "primary-type": "Album", "secondary-types": ["Live"]},
            {"id": "a3", "title": "Some EP", "primary-type": "EP"},
        ]
    }

    albums = fetch_studio_albums(client, BAND.mbid)

    assert [a["id"] for a in albums] == ["a1"]


def test_fetch_studio_albums_paginates_until_a_short_page():
    client = MagicMock()
    full_page = {
        "release-groups": [
            {"id": f"a{i}", "title": f"Album {i}", "primary-type": "Album"} for i in range(100)
        ]
    }
    short_page = {"release-groups": [{"id": "a100", "title": "Last", "primary-type": "Album"}]}
    client.get_release_groups.side_effect = [full_page, short_page]

    albums = fetch_studio_albums(client, BAND.mbid)

    assert len(albums) == 101
    assert client.get_release_groups.call_count == 2
    client.get_release_groups.assert_any_call(BAND.mbid, offset=0)
    client.get_release_groups.assert_any_call(BAND.mbid, offset=100)


# --- fetch_all_recordings --------------------------------------------------


def test_fetch_all_recordings_stops_when_offset_reaches_total():
    client = MagicMock()
    client.get_recordings.side_effect = [
        {"recordings": [{"id": "r1"}, {"id": "r2"}], "recording-count": 3},
        {"recordings": [{"id": "r3"}], "recording-count": 3},
    ]

    recordings = fetch_all_recordings(client, BAND.mbid)

    assert [r["id"] for r in recordings] == ["r1", "r2", "r3"]
    assert client.get_recordings.call_count == 2


def test_fetch_all_recordings_stops_on_empty_page():
    client = MagicMock()
    client.get_recordings.return_value = {"recordings": [], "recording-count": 0}

    recordings = fetch_all_recordings(client, BAND.mbid)

    assert recordings == []
    assert client.get_recordings.call_count == 1


# --- should_skip_band -------------------------------------------------------


def test_should_skip_band_false_when_no_prior_data():
    conn = MagicMock()
    _cursor(conn).fetchone.return_value = (None,)

    assert should_skip_band(conn, BAND.mbid) is False


def test_should_skip_band_true_when_recently_loaded():
    conn = MagicMock()
    recent = datetime.now(timezone.utc) - timedelta(days=1)
    _cursor(conn).fetchone.return_value = (recent,)

    assert should_skip_band(conn, BAND.mbid, refresh_after_days=DEFAULT_REFRESH_DAYS) is True


def test_should_skip_band_false_when_stale():
    conn = MagicMock()
    stale = datetime.now(timezone.utc) - timedelta(days=31)
    _cursor(conn).fetchone.return_value = (stale,)

    assert should_skip_band(conn, BAND.mbid, refresh_after_days=30) is False


# --- extract_band ------------------------------------------------------------


def test_extract_band_skips_entirely_when_data_is_fresh():
    client = MagicMock()
    conn = MagicMock()
    recent = datetime.now(timezone.utc) - timedelta(days=1)
    _cursor(conn).fetchone.return_value = (recent,)

    summary = extract_band(client, conn, BAND)

    assert summary == {"band": "Muse", "skipped": True, "albums": 0, "tracks": 0, "recordings": 0}
    client.get_release_groups.assert_not_called()
    client.get_recordings.assert_not_called()
    conn.commit.assert_not_called()


def test_extract_band_upserts_albums_tracks_and_recordings():
    client = MagicMock()
    conn = MagicMock()
    _cursor(conn).fetchone.return_value = (None,)  # never extracted before

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

    summary = extract_band(client, conn, BAND)

    assert summary == {"band": "Muse", "skipped": False, "albums": 1, "tracks": 2, "recordings": 1}

    executed = [call.args[0] for call in _cursor(conn).execute.call_args_list]
    assert any("INSERT INTO raw_musicbrainz.albums" in stmt for stmt in executed)
    assert sum("INSERT INTO raw_musicbrainz.album_tracks" in stmt for stmt in executed) == 2
    assert any("INSERT INTO raw_musicbrainz.recordings" in stmt for stmt in executed)
    assert all("ON CONFLICT" in stmt for stmt in executed if "INSERT" in stmt)
    conn.commit.assert_called_once()


def test_extract_band_skips_tracks_when_release_group_has_no_releases():
    client = MagicMock()
    conn = MagicMock()
    _cursor(conn).fetchone.return_value = (None,)

    client.get_release_groups.return_value = {
        "release-groups": [{"id": "rg1", "title": "Mystery Album", "primary-type": "Album"}]
    }
    client.get_releases_for_release_group.return_value = {"releases": []}
    client.get_recordings.return_value = {"recordings": [], "recording-count": 0}

    summary = extract_band(client, conn, BAND)

    assert summary == {"band": "Muse", "skipped": False, "albums": 1, "tracks": 0, "recordings": 0}
