import json
from unittest.mock import MagicMock, patch

import pytest

from encore.clients import _http
from encore.clients.musicbrainz import MusicBrainzClient


@pytest.fixture(autouse=True)
def _isolated_cache_dir(tmp_path, monkeypatch):
    """Every test gets its own empty cache dir, a clean counter, and no
    real sleeping (rate-limit delay and retry backoff are timing details,
    not behavior under test here)."""
    monkeypatch.setattr("encore.clients.musicbrainz.CACHE_DIR", tmp_path)
    monkeypatch.setattr("encore.clients._http.time.sleep", lambda _seconds: None)
    _http.reset_counters()
    yield
    _http.reset_counters()


def _mock_response(status_code: int, payload: dict | None = None) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = payload or {}
    if status_code >= 400:
        import requests

        response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=response
        )
    else:
        response.raise_for_status.side_effect = None
    return response


def test_real_request_increments_counter_and_writes_cache(tmp_path):
    client = MusicBrainzClient()
    ok = _mock_response(200, {"artists": [{"id": "abc", "score": 100}]})

    with patch.object(client._session, "get", return_value=ok) as mock_get:
        result = client.search_artist("Muse")

    assert result == {"artists": [{"id": "abc", "score": 100}]}
    assert mock_get.call_count == 1
    assert _http.get_counters() == {"musicbrainz": 1}

    cached_file = tmp_path / "search_artist_muse.json"
    assert cached_file.exists()
    assert json.loads(cached_file.read_text(encoding="utf-8")) == result


def test_cache_hit_skips_http_call_and_counter(tmp_path):
    cache_file = tmp_path / "search_artist_muse.json"
    cache_file.write_text(json.dumps({"artists": ["cached"]}), encoding="utf-8")

    client = MusicBrainzClient()
    with patch.object(client._session, "get") as mock_get:
        result = client.search_artist("Muse")

    assert result == {"artists": ["cached"]}
    mock_get.assert_not_called()
    assert _http.get_counters() == {}


def test_retries_on_429_then_succeeds():
    client = MusicBrainzClient()
    too_many = _mock_response(429)
    ok = _mock_response(200, {"recordings": [], "recording-count": 0})

    with patch("encore.clients._http.time.sleep") as mock_sleep:
        with patch.object(client._session, "get", side_effect=[too_many, ok]) as mock_get:
            result = client.get_recordings(mbid="some-mbid")

    assert result == {"recordings": [], "recording-count": 0}
    assert mock_get.call_count == 2
    # One counted attempt for the 429, one for the successful retry.
    assert _http.get_counters() == {"musicbrainz": 2}
    mock_sleep.assert_any_call(2)  # backoff before the retry


def test_pagination_uses_offset_and_limit_params():
    client = MusicBrainzClient()
    ok = _mock_response(200, {"recordings": [], "recording-count": 0})

    with patch.object(client._session, "get", return_value=ok) as mock_get:
        client.get_recordings(mbid="some-mbid", offset=200)

    _, kwargs = mock_get.call_args
    assert kwargs["params"]["offset"] == 200
    assert kwargs["params"]["limit"] == 100
    assert kwargs["params"]["artist"] == "some-mbid"
