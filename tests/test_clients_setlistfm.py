from unittest.mock import MagicMock, patch

import pytest
import requests

from encore.clients import _http
from encore.clients.setlistfm import SetlistFmClient


@pytest.fixture(autouse=True)
def _clean_counters_and_no_sleep(monkeypatch):
    monkeypatch.setattr("encore.clients._http.time.sleep", lambda _seconds: None)
    _http.reset_counters()
    yield
    _http.reset_counters()


def _mock_response(status_code: int, payload: dict | None = None) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = payload or {}
    response.raise_for_status.side_effect = (
        requests.exceptions.HTTPError(response=response) if status_code >= 400 else None
    )
    return response


def test_missing_api_key_raises_environment_error(monkeypatch):
    monkeypatch.delenv("SETLISTFM_API_KEY", raising=False)

    with pytest.raises(EnvironmentError):
        SetlistFmClient()


def test_session_carries_api_key_header(monkeypatch):
    monkeypatch.setenv("SETLISTFM_API_KEY", "secret-key")

    client = SetlistFmClient()

    assert client._session.headers["x-api-key"] == "secret-key"
    assert client._session.headers["Accept"] == "application/json"


def test_every_call_hits_the_network_no_disk_cache(monkeypatch, tmp_path):
    # Point cwd at an empty temp dir; if the client ever tried to read or
    # write a cache file relative to it, this test would still pass only
    # because there is none — the real guard is call_count == 2 below for
    # two calls with the *same* arguments, which a cache would collapse
    # to 1.
    monkeypatch.setenv("SETLISTFM_API_KEY", "secret-key")
    monkeypatch.chdir(tmp_path)
    client = SetlistFmClient()
    ok = _mock_response(200, {"setlist": [], "total": 0, "itemsPerPage": 20})

    with patch.object(client._session, "get", return_value=ok) as mock_get:
        client.get_artist_setlists(mbid="some-mbid", page=1)
        client.get_artist_setlists(mbid="some-mbid", page=1)

    assert mock_get.call_count == 2
    assert _http.get_counters() == {"setlistfm": 2}
    assert list(tmp_path.iterdir()) == []  # nothing written to disk


def test_pagination_param(monkeypatch):
    monkeypatch.setenv("SETLISTFM_API_KEY", "secret-key")
    client = SetlistFmClient()
    ok = _mock_response(200, {"setlist": [], "total": 0, "itemsPerPage": 20})

    with patch.object(client._session, "get", return_value=ok) as mock_get:
        client.get_artist_setlists(mbid="some-mbid", page=3)

    _, kwargs = mock_get.call_args
    assert kwargs["params"] == {"p": 3}


def test_retries_on_503_then_succeeds(monkeypatch):
    monkeypatch.setenv("SETLISTFM_API_KEY", "secret-key")
    client = SetlistFmClient()
    unavailable = _mock_response(503)
    ok = _mock_response(200, {"artist": []})

    with patch.object(client._session, "get", side_effect=[unavailable, ok]) as mock_get:
        result = client.search_artist("Muse")

    assert result == {"artist": []}
    assert mock_get.call_count == 2
    assert _http.get_counters() == {"setlistfm": 2}


def test_raises_after_max_retries_exhausted(monkeypatch):
    monkeypatch.setenv("SETLISTFM_API_KEY", "secret-key")
    client = SetlistFmClient()
    unavailable = _mock_response(503)

    with patch.object(client._session, "get", return_value=unavailable) as mock_get:
        with pytest.raises(RuntimeError):
            client.search_artist("Muse")

    assert mock_get.call_count == 3  # MAX_RETRIES
    assert _http.get_counters() == {"setlistfm": 3}
