from unittest.mock import MagicMock, patch

from encore.clients import _http
from encore.config import Band
from encore.ingestion.setlistfm import (
    MAX_REQUESTS_PER_RUN,
    STORE_RAW_JSON_ENV_VAR,
    extract_band,
    fetch_all_setlists,
    parse_setlist,
)

BAND = Band(name="Muse", mbid="9c9f1380-2516-4fc9-a3e6-f9f61941d090")
RUN_ID = "run-123"


def _cursor(conn) -> MagicMock:
    return conn.cursor.return_value.__enter__.return_value


def _sample_setlist(setlist_id="sl1", with_encore=True):
    sets = [
        {
            "song": [
                {"name": "New Born"},
                {"name": "Feeling Good", "cover": {"name": "Nina Simone"}},
            ]
        }
    ]
    if with_encore:
        sets.append({"encore": 1, "song": [{"name": "Knights of Cydonia", "tape": True}]})

    return {
        "id": setlist_id,
        "eventDate": "18-06-2001",
        "tour": {"name": "Origin of Symmetry Tour"},
        "venue": {
            "name": "Some Venue",
            "city": {
                "name": "Paris",
                "country": {"name": "France"},
            },
        },
        "url": f"https://www.setlist.fm/setlist/{setlist_id}.html",
        "sets": {"set": sets},
    }


# --- fetch_all_setlists -----------------------------------------------------


def _reset_counters():
    _http.reset_counters()


def test_fetch_all_setlists_paginates_until_short_page():
    _reset_counters()
    client = MagicMock()
    full_page = {"setlist": [_sample_setlist(f"sl{i}") for i in range(20)], "itemsPerPage": 20}
    short_page = {"setlist": [_sample_setlist("sl20")], "itemsPerPage": 20}
    client.get_artist_setlists.side_effect = [full_page, short_page]

    setlists = fetch_all_setlists(client, BAND.mbid)

    assert len(setlists) == 21
    assert client.get_artist_setlists.call_count == 2
    client.get_artist_setlists.assert_any_call(mbid=BAND.mbid, page=1)
    client.get_artist_setlists.assert_any_call(mbid=BAND.mbid, page=2)


def test_fetch_all_setlists_aborts_when_budget_reached():
    _reset_counters()
    _http._counters["setlistfm"] = MAX_REQUESTS_PER_RUN

    client = MagicMock()

    try:
        fetch_all_setlists(client, BAND.mbid)
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "budget" in str(exc)
    client.get_artist_setlists.assert_not_called()
    _reset_counters()


# --- parse_setlist -----------------------------------------------------------


def test_parse_setlist_splits_setlist_and_entries():
    setlist_row, entries = parse_setlist(_sample_setlist())

    assert setlist_row == {
        "setlist_id": "sl1",
        "event_date": "18-06-2001",
        "tour_name": "Origin of Symmetry Tour",
        "venue_name": "Some Venue",
        "city": "Paris",
        "country": "France",
        "setlistfm_url": "https://www.setlist.fm/setlist/sl1.html",
    }
    assert len(entries) == 3

    new_born, feeling_good, knights = entries
    assert new_born == {
        "set_idx": 0,
        "position": 1,
        "song_name": "New Born",
        "is_encore": False,
        "is_cover": False,
        "cover_artist": None,
        "is_tape": False,
    }
    assert feeling_good["is_cover"] is True
    assert feeling_good["cover_artist"] == "Nina Simone"
    assert knights["is_encore"] is True
    assert knights["is_tape"] is True
    assert knights["set_idx"] == 1
    assert knights["position"] == 1


def test_parse_setlist_handles_missing_optional_fields():
    minimal = {"id": "sl2", "sets": {}}

    setlist_row, entries = parse_setlist(minimal)

    assert setlist_row["setlist_id"] == "sl2"
    assert setlist_row["tour_name"] is None
    assert setlist_row["venue_name"] is None
    assert entries == []


# --- extract_band ------------------------------------------------------------


def test_extract_band_loads_setlists_and_entries_without_raw_json_by_default(monkeypatch):
    _reset_counters()
    monkeypatch.delenv(STORE_RAW_JSON_ENV_VAR, raising=False)
    client = MagicMock()
    conn = MagicMock()
    client.get_artist_setlists.return_value = {
        "setlist": [_sample_setlist("sl1")],
        "itemsPerPage": 20,
    }

    summary = extract_band(client, conn, BAND, RUN_ID)

    assert summary == {"band": "Muse", "setlists": 1, "entries": 3}
    executed = [call.args[0] for call in _cursor(conn).execute.call_args_list]
    assert sum("INSERT INTO raw_setlistfm.setlists" in stmt for stmt in executed) == 1
    assert sum("INSERT INTO raw_setlistfm.setlist_entries" in stmt for stmt in executed) == 3
    assert not any("raw_responses" in stmt for stmt in executed)
    conn.commit.assert_called_once()
    _reset_counters()


def test_extract_band_stores_raw_json_when_enabled(monkeypatch):
    _reset_counters()
    monkeypatch.setenv(STORE_RAW_JSON_ENV_VAR, "true")
    client = MagicMock()
    conn = MagicMock()
    client.get_artist_setlists.return_value = {
        "setlist": [_sample_setlist("sl1")],
        "itemsPerPage": 20,
    }

    extract_band(client, conn, BAND, RUN_ID)

    executed = [call.args[0] for call in _cursor(conn).execute.call_args_list]
    assert any("raw_responses" in stmt for stmt in executed)
    _reset_counters()
