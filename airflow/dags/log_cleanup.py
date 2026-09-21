"""Airflow log cleanup (spec-01 R1.6): removes files under
/opt/airflow/logs older than encore.log_cleanup.MAX_LOG_AGE_DAYS.

A separate daily DAG rather than a task inside encore_pipeline — log
retention runs on its own cadence, independent of the monthly ingestion
schedule, and keeps running regardless of whether encore_pipeline runs,
fails, or is paused.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path

from airflow.sdk import dag, task

from encore.log_cleanup import MAX_LOG_AGE_DAYS, delete_old_logs

logger = logging.getLogger(__name__)

LOGS_DIR = Path(os.environ.get("AIRFLOW_LOGS_DIR", "/opt/airflow/logs"))


@dag(
    dag_id="log_cleanup",
    schedule="@daily",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["encore", "maintenance"],
    # Unlike every other DAG (created paused, docker-compose.yml), this one
    # must be active from the start, everywhere: it is what deletes task logs
    # that may contain setlist.fm titles (transform diagnostic report).
    is_paused_upon_creation=False,
)
def log_cleanup():
    @task
    def clean_airflow_logs() -> int:
        deleted = delete_old_logs(LOGS_DIR)
        logger.info("Deleted %d log file(s) older than %d days", len(deleted), MAX_LOG_AGE_DAYS)
        return len(deleted)

    clean_airflow_logs()


log_cleanup()
