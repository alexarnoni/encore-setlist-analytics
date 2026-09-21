"""Airflow log cleanup logic (spec-01 R1.6).

Pure filesystem logic, no Airflow import — kept in src/encore/ so it's
covered by the fast unit test suite; airflow/dags/log_cleanup.py just
wraps `delete_old_logs` in a daily DAG task.
"""

from __future__ import annotations

import time
from pathlib import Path

MAX_LOG_AGE_DAYS = 14


def delete_old_logs(logs_dir: Path, max_age_days: int = MAX_LOG_AGE_DAYS) -> list[Path]:
    """
    Delete every file under `logs_dir` whose mtime is older than
    `max_age_days`, then remove any directory left empty as a result
    (Airflow nests one log directory per dag/task/run, so without this
    the tree accumulates empty folders forever). Returns the deleted
    file paths.

    A missing `logs_dir` is treated as "nothing to clean" rather than an
    error, so this is safe to call before Airflow has ever written a log.
    """
    if not logs_dir.exists():
        return []

    cutoff = time.time() - max_age_days * 86400
    deleted: list[Path] = []

    # Deepest paths first, so a directory's files are gone by the time
    # we consider removing the (now possibly empty) directory itself.
    for path in sorted(logs_dir.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if path.is_file():
            if path.stat().st_mtime < cutoff:
                path.unlink()
                deleted.append(path)
        elif path.is_dir():
            try:
                path.rmdir()  # no-op failure if not actually empty
            except OSError:
                pass

    return deleted
