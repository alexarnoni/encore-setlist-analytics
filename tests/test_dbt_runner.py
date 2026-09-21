import logging
import shutil
import subprocess
import sys

import pytest

from encore import dbt_runner
from encore.dbt_runner import DbtError, dbt_binary, run_dbt, run_transform

# The "dbt" executable is the Python interpreter itself, so a command is a
# real subprocess that we can make print or fail on demand, on any OS.
PY = sys.executable


def test_dbt_binary_uses_the_venv_from_the_environment(monkeypatch):
    monkeypatch.setenv("DBT_VENV", "/somewhere/venv")

    assert dbt_binary().replace("\\", "/") == "/somewhere/venv/bin/dbt"


def test_dbt_binary_defaults_to_the_image_venv(monkeypatch):
    monkeypatch.delenv("DBT_VENV", raising=False)

    assert dbt_binary().replace("\\", "/") == "/opt/dbt-venv/bin/dbt"


def test_run_dbt_streams_stdout_and_stderr_to_the_log(caplog):
    code = "import sys; print('to stdout'); print('to stderr', file=sys.stderr)"

    with caplog.at_level(logging.INFO, logger="encore.dbt_runner"):
        run_dbt(["-c", code], executable=PY)

    messages = [record.getMessage() for record in caplog.records]
    assert "[dbt] to stdout" in messages
    assert "[dbt] to stderr" in messages


def test_run_dbt_raises_with_the_exit_code_on_failure():
    with pytest.raises(DbtError) as excinfo:
        run_dbt(["-c", "import sys; sys.exit(3)"], executable=PY)

    assert excinfo.value.returncode == 3
    assert "exit code 3" in str(excinfo.value)


def test_run_dbt_still_logs_output_of_a_failing_command(caplog):
    code = "import sys; print('boom'); sys.exit(1)"

    with caplog.at_level(logging.INFO, logger="encore.dbt_runner"):
        with pytest.raises(DbtError):
            run_dbt(["-c", code], executable=PY)

    assert "[dbt] boom" in [record.getMessage() for record in caplog.records]


def test_run_transform_runs_seed_run_test_in_order(monkeypatch):
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(
        dbt_runner, "run_dbt", lambda command, **_: calls.append(tuple(command))
    )

    run_transform()

    assert calls == [("seed", "--full-refresh"), ("run",), ("test",)]


def test_run_transform_stops_at_the_first_failing_step(monkeypatch):
    calls: list[tuple[str, ...]] = []

    def fake_run_dbt(command, **_):
        calls.append(tuple(command))
        if tuple(command) == ("run",):
            raise DbtError(command, 1)

    monkeypatch.setattr(dbt_runner, "run_dbt", fake_run_dbt)

    with pytest.raises(DbtError):
        run_transform()

    assert calls == [("seed", "--full-refresh"), ("run",)]  # `test` never ran


# --- project version logged at the start of a transform --------------------


def _project(tmp_path):
    root = tmp_path / "dbt"
    (root / "models").mkdir(parents=True)
    (root / "dbt_project.yml").write_text("name: encore\n")
    (root / "models" / "a.sql").write_text("select 1\n")
    return root


def test_fingerprint_is_stable_and_follows_file_contents(tmp_path):
    root = _project(tmp_path)
    first = dbt_runner.dbt_project_fingerprint(root)

    assert first == dbt_runner.dbt_project_fingerprint(root)
    assert len(first) == 12

    (root / "models" / "a.sql").write_text("select 2\n")
    changed = dbt_runner.dbt_project_fingerprint(root)
    assert changed != first

    (root / "models" / "b.sql").write_text("select 3\n")
    assert dbt_runner.dbt_project_fingerprint(root) != changed


def test_fingerprint_ignores_dbt_output_and_user_file(tmp_path):
    root = _project(tmp_path)
    before = dbt_runner.dbt_project_fingerprint(root)

    (root / "target").mkdir()
    (root / "target" / "manifest.json").write_text("{}")
    (root / "logs").mkdir()
    (root / "logs" / "dbt.log").write_text("noise")
    (root / ".user.yml").write_text("id: 1\n")

    assert dbt_runner.dbt_project_fingerprint(root) == before


def test_fingerprint_of_a_missing_directory(tmp_path):
    assert dbt_runner.dbt_project_fingerprint(tmp_path / "nope") == "missing"


def test_commit_prefers_the_value_baked_into_the_image(monkeypatch, tmp_path):
    monkeypatch.setenv("ENCORE_DBT_COMMIT", "abc1234")

    assert dbt_runner.dbt_project_commit(tmp_path) == "abc1234"


def test_commit_is_unknown_when_nothing_is_baked_and_git_is_unavailable(monkeypatch, tmp_path):
    monkeypatch.setenv("ENCORE_DBT_COMMIT", "unknown")

    def no_git(*args, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(dbt_runner.subprocess, "run", no_git)

    assert dbt_runner.dbt_project_commit(tmp_path) == "unknown"


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_commit_falls_back_to_git_in_a_checkout(monkeypatch, tmp_path):
    monkeypatch.delenv("ENCORE_DBT_COMMIT", raising=False)
    root = _project(tmp_path)
    git = ["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "."], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "init"], check=True)
    expected = subprocess.run(
        [*git, "log", "-1", "--format=%h"], capture_output=True, text=True, check=True
    ).stdout.strip()

    assert dbt_runner.dbt_project_commit(root) == expected


def test_log_dbt_project_version_reports_commit_and_content_hash(monkeypatch, tmp_path, caplog):
    root = _project(tmp_path)
    monkeypatch.setenv("ENCORE_DBT_COMMIT", "abc1234")

    with caplog.at_level(logging.INFO, logger="encore.dbt_runner"):
        dbt_runner.log_dbt_project_version(root)

    message = caplog.records[-1].getMessage()
    assert "commit=abc1234" in message
    assert f"content_sha={dbt_runner.dbt_project_fingerprint(root)}" in message


def test_run_transform_logs_the_version_before_any_dbt_step(monkeypatch):
    events: list = []
    monkeypatch.setattr(dbt_runner, "log_dbt_project_version", lambda *a, **k: events.append("version"))
    monkeypatch.setattr(dbt_runner, "run_dbt", lambda command, **_: events.append(tuple(command)))

    run_transform()

    assert events == ["version", ("seed", "--full-refresh"), ("run",), ("test",)]
