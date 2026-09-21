"""Run dbt commands from the pipeline and surface their output in the logs.

dbt lives in its own virtualenv inside the Airflow image (see
airflow/Dockerfile) and is deliberately not on PATH, so it is called by full
path. Its stdout/stderr are streamed line by line through the logging module,
which is what makes dbt's output show up in the Airflow task log (spec-02a
R8.4) while the command is still running, not only at the end.
"""

from __future__ import annotations

import logging
import os
import subprocess
from collections.abc import Sequence

logger = logging.getLogger(__name__)

DEFAULT_DBT_VENV = "/opt/dbt-venv"

# The dbt steps of one transform, in order. `seed` runs on every transform
# rather than only when the CSVs changed: it is idempotent and takes well
# under a second for two small files (spec-02a open question 2).
TRANSFORM_STEPS: tuple[tuple[str, ...], ...] = (("seed",), ("run",), ("test",))


class DbtError(RuntimeError):
    """A dbt command exited non-zero."""

    def __init__(self, command: Sequence[str], returncode: int) -> None:
        self.command = tuple(command)
        self.returncode = returncode
        super().__init__(f"`dbt {' '.join(command)}` failed with exit code {returncode}")


def dbt_binary() -> str:
    """Full path of the dbt executable inside the isolated venv."""
    return os.path.join(os.environ.get("DBT_VENV", DEFAULT_DBT_VENV), "bin", "dbt")


def run_dbt(command: Sequence[str], *, executable: str | None = None) -> None:
    """
    Run one dbt command, logging its output live.

    Project and profiles directories, target/log paths and the usage-stats
    opt-out come from DBT_* environment variables set in the Airflow image
    (including DBT_USE_COLORS=false, so the task log has no ANSI escape
    codes), so `command` is just the dbt subcommand and its flags.

    Raises:
        DbtError: if dbt exits with a non-zero status.
    """
    argv = [executable or dbt_binary(), *command]
    logger.info("Running: dbt %s", " ".join(command))
    with subprocess.Popen(
        argv,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
    ) as process:
        assert process.stdout is not None  # guaranteed by stdout=PIPE
        for line in process.stdout:
            logger.info("[dbt] %s", line.rstrip())
    if process.returncode != 0:
        raise DbtError(command, process.returncode)


def run_transform(*, executable: str | None = None) -> None:
    """
    Run `dbt seed`, `dbt run` and `dbt test`, stopping at the first failure.

    Not transactional: `dbt run` has already replaced the analytics tables
    by the time `dbt test` runs, so a failing test leaves the freshly built
    tables in place and fails the pipeline rather than rolling them back.
    """
    for step in TRANSFORM_STEPS:
        run_dbt(step, executable=executable)
