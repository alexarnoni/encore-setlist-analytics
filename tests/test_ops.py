from datetime import datetime, timezone
from unittest.mock import MagicMock

from encore.ops import ensure_tables, log_run


def _cursor(conn) -> MagicMock:
    return conn.cursor.return_value.__enter__.return_value


def test_ensure_tables_creates_pipeline_runs():
    conn = MagicMock()

    ensure_tables(conn)

    executed = _cursor(conn).execute.call_args[0][0]
    assert "CREATE TABLE IF NOT EXISTS ops.pipeline_runs" in executed
    conn.commit.assert_called_once()


def test_log_run_inserts_with_upsert_on_run_id():
    conn = MagicMock()
    started = datetime(2026, 1, 1, tzinfo=timezone.utc)
    finished = datetime(2026, 1, 1, 0, 30, tzinfo=timezone.utc)

    log_run(
        conn,
        run_id="run-1",
        started_at=started,
        finished_at=finished,
        status="success",
        setlistfm_requests=475,
        musicbrainz_requests=120,
        setlists_per_band={"Muse": 1722, "Oasis": 958},
        error_message=None,
    )

    sql, params = _cursor(conn).execute.call_args[0]
    assert "INSERT INTO ops.pipeline_runs" in sql
    assert "ON CONFLICT (run_id) DO UPDATE" in sql
    assert params[0] == "run-1"
    assert params[3] == "success"
    assert params[4] == 475
    assert params[5] == 120
    assert '"Muse": 1722' in params[6]
    assert params[7] is None
    conn.commit.assert_called_once()


def test_log_run_serializes_error_message_on_failure():
    conn = MagicMock()
    now = datetime.now(timezone.utc)

    log_run(
        conn,
        run_id="run-2",
        started_at=now,
        finished_at=now,
        status="failed",
        setlistfm_requests=10,
        musicbrainz_requests=0,
        setlists_per_band={},
        error_message="setlist.fm request budget exceeded",
    )

    _, params = _cursor(conn).execute.call_args[0]
    assert params[3] == "failed"
    assert params[7] == "setlist.fm request budget exceeded"
