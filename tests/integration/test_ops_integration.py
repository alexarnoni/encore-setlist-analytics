"""Integration coverage for encore.ops against a real PostgreSQL (R7)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from encore import ops


@pytest.fixture()
def clean_pipeline_runs(pg_connection):
    ops.ensure_tables(pg_connection)
    with pg_connection.cursor() as cur:
        cur.execute("TRUNCATE ops.pipeline_runs")
    pg_connection.commit()
    return pg_connection


def test_log_run_upserts_on_run_id(clean_pipeline_runs):
    conn = clean_pipeline_runs
    now = datetime.now(timezone.utc)

    ops.log_run(
        conn, run_id="run-1", started_at=now, finished_at=now, status="success",
        setlistfm_requests=475, musicbrainz_requests=120,
        setlists_per_band={"Muse": 1722}, error_message=None,
    )
    ops.log_run(
        conn, run_id="run-1", started_at=now, finished_at=now, status="failed",
        setlistfm_requests=999, musicbrainz_requests=1,
        setlists_per_band={}, error_message="boom",
    )

    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM ops.pipeline_runs")
        assert cur.fetchone()[0] == 1
        cur.execute(
            "SELECT status, setlistfm_requests, error_message FROM ops.pipeline_runs "
            "WHERE run_id = 'run-1'"
        )
        assert cur.fetchone() == ("failed", 999, "boom")


def test_sum_setlistfm_requests_today_only_counts_today(clean_pipeline_runs):
    conn = clean_pipeline_runs
    today = datetime.now(timezone.utc)
    yesterday = today - timedelta(days=1)

    ops.log_run(
        conn, run_id="today-run", started_at=today, finished_at=today, status="success",
        setlistfm_requests=300, musicbrainz_requests=0, setlists_per_band={},
    )
    ops.log_run(
        conn, run_id="yesterday-run", started_at=yesterday, finished_at=yesterday,
        status="success", setlistfm_requests=1000, musicbrainz_requests=0,
        setlists_per_band={},
    )

    assert ops.sum_setlistfm_requests_today(conn) == 300


def test_estimate_next_run_cost_uses_latest_successful_run(clean_pipeline_runs):
    conn = clean_pipeline_runs
    now = datetime.now(timezone.utc)

    ops.log_run(
        conn, run_id="older-success", started_at=now - timedelta(days=60),
        finished_at=now - timedelta(days=60), status="success",
        setlistfm_requests=400, musicbrainz_requests=0, setlists_per_band={},
    )
    ops.log_run(
        conn, run_id="newer-success", started_at=now - timedelta(days=30),
        finished_at=now - timedelta(days=30), status="success",
        setlistfm_requests=475, musicbrainz_requests=0, setlists_per_band={},
    )
    ops.log_run(
        conn, run_id="newest-failed", started_at=now, finished_at=now,
        status="failed", setlistfm_requests=50, musicbrainz_requests=0,
        setlists_per_band={},
    )

    # Most recent *successful* run wins, not just the most recent row.
    assert ops.estimate_next_run_setlistfm_cost(conn) == 475
