"""Encore monthly ingestion pipeline (spec-01 R6).

Loads MusicBrainz discography (persistent) and each band's full
setlist.fm history (ephemeral) into PostgreSQL, validates the load, builds
the analytics marts with dbt (spec-02a), and truncates raw_setlistfm — both
at the start (so a previous run's leftovers never leak into this run's
validation) and at the end, with trigger_rule=all_done so it also runs when
an earlier task fails (adjustment 6).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime

from airflow.sdk import TriggerRule, dag, get_current_context, task
from airflow.sdk.exceptions import AirflowFailException
from airflow.utils import timezone as airflow_timezone

from encore import ops
from encore.clients._http import get_counters, reset_counters
from encore.clients.musicbrainz import MusicBrainzClient
from encore.clients.setlistfm import SetlistFmClient
from encore.config import Band, load_bands
from encore.db import ensure_schemas, get_connection
from encore.dbt_runner import DbtError, run_transform
from encore.ingestion import musicbrainz as mb_ingestion
from encore.ingestion import setlistfm as sf_ingestion

logger = logging.getLogger(__name__)

MAX_DAILY_SETLISTFM_REQUESTS = 1300
DEFAULT_LAST_RUN_ESTIMATE = 475


def _filtered_bands() -> list[Band]:
    """All 7 bands, or a subset via ENCORE_BANDS_FILTER (adjustment 11)."""
    bands = load_bands()
    wanted = os.environ.get("ENCORE_BANDS_FILTER", "").strip()
    if not wanted:
        return bands
    names = {name.strip() for name in wanted.split(",") if name.strip()}
    return [band for band in bands if band.name in names]


@dag(
    dag_id="encore_pipeline",
    schedule="@monthly",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["encore", "ingestion", "dbt"],
)
def encore_pipeline():
    @task
    def truncate_raw_setlistfm_start() -> None:
        conn = get_connection()
        try:
            ensure_schemas(conn)
            sf_ingestion.ensure_tables(conn)
            mb_ingestion.ensure_tables(conn)
            ops.ensure_tables(conn)
            sf_ingestion.truncate_all(conn)
        finally:
            conn.close()

    @task
    def check_api_budget() -> None:
        conn = get_connection()
        try:
            today = ops.sum_setlistfm_requests_today(conn)
            estimate = ops.estimate_next_run_setlistfm_cost(
                conn, default=DEFAULT_LAST_RUN_ESTIMATE
            )
        finally:
            conn.close()

        projected = today + estimate
        if projected > MAX_DAILY_SETLISTFM_REQUESTS:
            raise AirflowFailException(
                f"Projected setlist.fm requests today ({projected} = "
                f"{today} already logged + {estimate} estimated for this "
                f"run) would exceed the daily budget of "
                f"{MAX_DAILY_SETLISTFM_REQUESTS}."
            )

    @task
    def extract_musicbrainz() -> dict:
        reset_counters()
        client = MusicBrainzClient()
        conn = get_connection()
        try:
            summaries = [mb_ingestion.extract_band(client, conn, band) for band in _filtered_bands()]
        finally:
            conn.close()
        return {"summaries": summaries, "requests": get_counters().get("musicbrainz", 0)}

    @task(max_active_tis_per_dag=1)
    def extract_setlistfm(band_dict: dict) -> dict:
        # Count only THIS band's requests. When tasks share a process (as in
        # `airflow dags test`) the counters would otherwise accumulate across
        # bands and log_run would sum running totals.
        reset_counters()
        run_id = get_current_context()["run_id"]
        band = Band(**band_dict)
        client = SetlistFmClient()
        conn = get_connection()
        try:
            summary = sf_ingestion.extract_band(client, conn, band, run_id)
        finally:
            conn.close()
        summary["requests"] = get_counters().get("setlistfm", 0)
        return summary

    @task
    def validate_raw(setlistfm_summaries: list[dict]) -> list[dict]:
        conn = get_connection()
        try:
            results = sf_ingestion.validate_bands(conn, _filtered_bands())
        except ValueError as exc:
            raise AirflowFailException(str(exc)) from exc
        finally:
            conn.close()

        for result in results:
            logger.info(
                "%s: %s/%s setlists with songs (%.1f%%)",
                result["band"],
                result["setlists_with_songs"],
                result["total_setlists"],
                result["pct_with_songs"],
            )
        return results

    @task
    def transform() -> bool:
        """
        Build the marts with dbt (spec-02a R8): seed, run, test.

        Runs after validation and before cleanup, while raw_setlistfm still
        holds this run's data. A dbt failure raises AirflowFailException
        (no retry: the same data would fail the same way), which fails the
        run; cleanup_raw_setlistfm still executes (trigger_rule=all_done).
        """
        try:
            run_transform()
        except DbtError as exc:
            raise AirflowFailException(str(exc)) from exc
        return True

    @task(trigger_rule=TriggerRule.ALL_DONE)
    def cleanup_raw_setlistfm() -> None:
        conn = get_connection()
        try:
            sf_ingestion.truncate_all(conn)
        finally:
            conn.close()

    @task(trigger_rule=TriggerRule.ALL_DONE)
    def log_run(
        mb_result: dict | None,
        sf_results: list[dict | None],
        validated: list[dict] | None,
        transformed: bool | None,
    ) -> None:
        """
        Write this run's summary to ops.pipeline_runs (R6.7).

        v1 success heuristic: a task that raised never pushes an XCom,
        so any argument still being None/missing here means its task (or
        one of its mapped instances) failed — good enough for spec-01's
        skeleton DAG. `transform()` returns True on success specifically
        so a raised exception there (transformed=None) isn't
        indistinguishable from success (unlike a bare `None` return
        would be).
        """
        context = get_current_context()
        dag_run = context["dag_run"]

        clean_sf_results = [r for r in sf_results if r]
        sf_requests = sum(r.get("requests", 0) for r in clean_sf_results)
        mb_requests = mb_result.get("requests", 0) if mb_result else 0
        setlists_per_band = {r["band"]: r.get("setlists", 0) for r in clean_sf_results}

        succeeded = (
            mb_result is not None
            and validated is not None
            and transformed is True
            and all(r is not None for r in sf_results)
        )

        conn = get_connection()
        try:
            ops.log_run(
                conn,
                run_id=dag_run.run_id,
                started_at=dag_run.start_date,
                finished_at=airflow_timezone.utcnow(),
                status="success" if succeeded else "failed",
                setlistfm_requests=sf_requests,
                musicbrainz_requests=mb_requests,
                setlists_per_band=setlists_per_band,
                error_message=None if succeeded else "one or more upstream tasks failed; see task logs",
            )
        finally:
            conn.close()

    bands_as_dicts = [{"name": band.name, "mbid": band.mbid} for band in _filtered_bands()]

    truncate_start = truncate_raw_setlistfm_start()
    budget = check_api_budget()
    mb_result = extract_musicbrainz()
    sf_results = extract_setlistfm.expand(band_dict=bands_as_dicts)
    validated = validate_raw(sf_results)
    transformed = transform()
    cleanup = cleanup_raw_setlistfm()
    logged = log_run(mb_result, sf_results, validated, transformed)

    truncate_start >> budget >> mb_result >> sf_results >> validated >> transformed
    [validated, transformed] >> cleanup >> logged


encore_pipeline()
