"""Run log for the pipeline: ops.pipeline_runs (spec-01 R7).

One row per DAG run, written once at the end by the `log_run` task
(R6.7) with everything the run needs to be auditable: timing, status,
request counts per API, setlists loaded per band, and the error message
if the run failed.
"""

from __future__ import annotations

import json
from datetime import datetime


def ensure_tables(conn) -> None:
    """Create ops.pipeline_runs if it doesn't exist yet (idempotent)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS ops.pipeline_runs (
                run_id TEXT PRIMARY KEY,
                started_at TIMESTAMPTZ NOT NULL,
                finished_at TIMESTAMPTZ NOT NULL,
                status TEXT NOT NULL,
                setlistfm_requests INTEGER NOT NULL,
                musicbrainz_requests INTEGER NOT NULL,
                setlists_per_band JSONB NOT NULL,
                error_message TEXT
            )
            """
        )
    conn.commit()


def sum_setlistfm_requests_today(conn) -> int:
    """
    Real setlist.fm requests already logged today across all runs
    (spec-01 R6/adjustment 7's check_api_budget input #1).
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COALESCE(SUM(setlistfm_requests), 0)
            FROM ops.pipeline_runs
            WHERE started_at >= date_trunc('day', now())
            """
        )
        (total,) = cur.fetchone()
    return int(total)


def estimate_next_run_setlistfm_cost(conn, default: int = 475) -> int:
    """
    Estimate this run's setlist.fm request cost from the last
    successful run (adjustment 7's input #2); `default` (475, the full
    7-band load per tech.md) is used when there is no successful run
    yet to estimate from.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT setlistfm_requests FROM ops.pipeline_runs
            WHERE status = 'success'
            ORDER BY finished_at DESC
            LIMIT 1
            """
        )
        row = cur.fetchone()
    return row[0] if row else default


def log_run(
    conn,
    *,
    run_id: str,
    started_at: datetime,
    finished_at: datetime,
    status: str,
    setlistfm_requests: int,
    musicbrainz_requests: int,
    setlists_per_band: dict[str, int],
    error_message: str | None = None,
) -> None:
    """
    Write one run's summary to ops.pipeline_runs.

    Upserts on `run_id` so a task that retries and re-logs the same run
    doesn't create duplicate rows.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO ops.pipeline_runs
                (run_id, started_at, finished_at, status, setlistfm_requests,
                 musicbrainz_requests, setlists_per_band, error_message)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (run_id) DO UPDATE SET
                finished_at = EXCLUDED.finished_at,
                status = EXCLUDED.status,
                setlistfm_requests = EXCLUDED.setlistfm_requests,
                musicbrainz_requests = EXCLUDED.musicbrainz_requests,
                setlists_per_band = EXCLUDED.setlists_per_band,
                error_message = EXCLUDED.error_message
            """,
            (
                run_id,
                started_at,
                finished_at,
                status,
                setlistfm_requests,
                musicbrainz_requests,
                json.dumps(setlists_per_band),
                error_message,
            ),
        )
    conn.commit()
