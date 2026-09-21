import logging
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
