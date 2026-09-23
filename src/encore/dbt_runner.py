"""Run dbt commands from the pipeline and surface their output in the logs.

dbt lives in its own virtualenv inside the Airflow image (see
airflow/Dockerfile) and is deliberately not on PATH, so it is called by full
path. Its stdout/stderr are streamed line by line through the logging module,
which is what makes dbt's output show up in the Airflow task log (spec-02a
R8.4) while the command is still running, not only at the end.
"""

from __future__ import annotations

import hashlib
import logging
import os
import subprocess
from collections.abc import Sequence
from pathlib import Path

from encore.transform_report import log_transform_report

logger = logging.getLogger(__name__)

DEFAULT_DBT_VENV = "/opt/dbt-venv"
DEFAULT_DBT_PROJECT_DIR = "/opt/airflow/dbt"

# Left out of the content fingerprint: dbt's own output and VCS metadata.
_FINGERPRINT_SKIP_DIRS = frozenset({"target", "logs", "dbt_packages", "__pycache__", ".git"})
_FINGERPRINT_SKIP_FILES = frozenset({".user.yml"})

# The dbt steps of one transform, in order. `seed` runs on every transform
# rather than only when the CSVs changed: it takes well under a second for
# two small files (spec-02a open question 2). It uses --full-refresh because
# a plain `dbt seed` only truncates and reloads an existing table and never
# adds a column: after a seed gained a column it would "load" fine (0 rows
# when the seed is header-only) yet leave the table without it.
#
# The test step excludes tag:survival (spec-03 design decision D1): those
# tests cover analytics.mart_song_survival/mart_survival_curves/
# mart_survival_summary, which the `analyze` task writes AFTER `transform` —
# on a fresh database they don't exist yet when this step runs, and even once
# they do, testing last run's content here would be pointless.
# `SURVIVAL_TEST_SELECTOR`/`run_analyze` below cover them once `analyze` has
# written this run's content.
TRANSFORM_STEPS: tuple[tuple[str, ...], ...] = (
    ("seed", "--full-refresh"),
    ("run",),
    ("test", "--exclude", "tag:survival"),
)

SURVIVAL_TEST_SELECTOR: tuple[str, ...] = ("test", "--select", "tag:survival")


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


def dbt_project_dir() -> Path:
    """Directory of the dbt project the pipeline runs (DBT_PROJECT_DIR)."""
    return Path(os.environ.get("DBT_PROJECT_DIR", DEFAULT_DBT_PROJECT_DIR))


def dbt_project_fingerprint(project_dir: Path | None = None) -> str:
    """
    Short hash of the dbt project's actual file contents.

    Unlike a commit hash it tells the truth when `./dbt` is bind-mounted in
    local development and files have been edited since the stack started.
    Skips dbt's own output (target/, logs/) so running dbt does not change it.
    Returns "missing" when the directory does not exist.
    """
    root = project_dir or dbt_project_dir()
    if not root.is_dir():
        return "missing"
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        relative = path.relative_to(root)
        if _FINGERPRINT_SKIP_DIRS.intersection(relative.parts[:-1]):
            continue
        if path.name in _FINGERPRINT_SKIP_FILES:
            continue
        digest.update(relative.as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()[:12]


def dbt_project_commit(project_dir: Path | None = None) -> str:
    """
    Git commit of the dbt project, or "unknown".

    The Airflow image has no .git, so the commit is baked in at build time
    through ENCORE_DBT_COMMIT (a `dev-mount` / `<hash>-dirty` value in local
    development). Failing that, ask git about the project directory, which
    works when running from a repository checkout.
    """
    baked = os.environ.get("ENCORE_DBT_COMMIT", "").strip()
    if baked and baked != "unknown":
        return baked
    try:
        result = subprocess.run(
            ["git", "-C", str(project_dir or dbt_project_dir()), "log", "-1", "--format=%h", "--", "."],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return result.stdout.strip() or "unknown"


def log_dbt_project_version(project_dir: Path | None = None) -> None:
    """Log which dbt project this run uses: commit and content hash."""
    logger.info(
        "dbt project: commit=%s content_sha=%s dir=%s",
        dbt_project_commit(project_dir),
        dbt_project_fingerprint(project_dir),
        project_dir or dbt_project_dir(),
    )


def run_transform(*, executable: str | None = None) -> None:
    """
    Run `dbt seed`, `dbt run` and `dbt test`, stopping at the first failure.

    The first thing logged is which dbt project version this is (commit and
    content hash), so a run's log always says what code produced its marts.
    The last is a diagnostic report (top undated catalog songs and top
    unmatched titles per band) written to the log only, never stored.

    Not transactional: `dbt run` has already replaced the analytics tables
    by the time `dbt test` runs, so a failing test leaves the freshly built
    tables in place and fails the pipeline rather than rolling them back.
    """
    log_dbt_project_version()
    *build_steps, test_step = TRANSFORM_STEPS
    for step in build_steps:
        run_dbt(step, executable=executable)
    try:
        run_dbt(test_step, executable=executable)
    finally:
        # After the tests, pass or fail: raw data is deleted right after
        # this task, so this is the only chance to log which titles are
        # behind the numbers (and a failing test is when they help most).
        # Skipped if seed/run failed: the views may not be consistent.
        # Best effort and log-only; see encore.transform_report.
        log_transform_report()


def run_analyze(*, executable: str | None = None) -> None:
    """
    Run the survival analysis (spec-03 Part B), between `transform` and
    `cleanup_raw_setlistfm`: writes analytics.mart_song_survival /
    mart_survival_curves / mart_survival_summary directly (design decision
    D4 — not a dbt model), then runs the dbt tests tagged `survival` against
    what was just written.

    Reads intermediate.int_show_song_sets and intermediate.int_performances,
    views over this run's raw setlist.fm data, so this must run while
    `raw_setlistfm` still has it — the same window `transform` has, and
    before `cleanup_raw_setlistfm`.

    Either step raising propagates: the caller (the `analyze` Airflow task)
    is responsible for turning that into a failed task. `cleanup_raw_setlistfm`
    and `log_run` have `trigger_rule=all_done`, so they still run either way.
    """
    from encore.analysis.io import write_survival_marts
    from encore.db import get_connection

    conn = get_connection()
    try:
        song_rows, curve_rows, summary_rows = write_survival_marts(conn)
        logger.info(
            "Survival marts written: %d song rows, %d curve rows, %d summary rows",
            song_rows, curve_rows, summary_rows,
        )
    finally:
        conn.close()
    run_dbt(SURVIVAL_TEST_SELECTOR, executable=executable)
