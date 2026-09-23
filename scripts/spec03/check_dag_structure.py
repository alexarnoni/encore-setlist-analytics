"""One-off structural check of encore_pipeline's task graph (spec-03 T10).

Airflow's SDK is only importable inside the Airflow image, and this project
has no metadata database dedicated to the spec-03 branch (spinning one up
would mean a whole second isolated Airflow stack, which the DAG-execution
checks below don't need) — so this asserts on the DAG object itself
(dependencies, trigger rules), not a real scheduled run. Run inside the
image, with src/ and airflow/dags/ from the WORKTREE mounted read-only,
never against the main stack:

    source scripts/spec03/env.sh
    docker run --rm --network spec03-net \
      -v "$PWD/src:/opt/airflow/src:ro" -v "$PWD/airflow/dags:/opt/airflow/dags:ro" \
      --entrypoint python encore-airflow:3.3.2 /opt/airflow/scripts/spec03/check_dag_structure.py
"""

import sys

sys.path.insert(0, "/opt/airflow/dags")

from airflow.sdk import TriggerRule  # noqa: E402

from encore_pipeline import encore_pipeline  # noqa: E402


def main() -> None:
    dag = encore_pipeline()
    tasks = dag.task_dict

    expected_order = [
        "truncate_raw_setlistfm_start",
        "check_api_budget",
        "extract_musicbrainz",
        "extract_setlistfm",
        "validate_raw",
        "transform",
        "analyze",
        "cleanup_raw_setlistfm",
        "log_run",
    ]
    assert set(tasks) == set(expected_order), sorted(set(tasks) ^ set(expected_order))
    print("task ids match:", expected_order)

    def assert_edge(upstream: str, downstream: str) -> None:
        assert downstream in tasks[upstream].downstream_task_ids, (upstream, downstream)
        assert upstream in tasks[downstream].upstream_task_ids, (upstream, downstream)

    # `analyze` sits between `transform` and `cleanup_raw_setlistfm`.
    assert_edge("transform", "analyze")
    assert_edge("analyze", "cleanup_raw_setlistfm")
    assert_edge("validate_raw", "transform")
    print("analyze is wired between transform and cleanup_raw_setlistfm")

    # cleanup must wait for `analyzed`, not just `transformed` (the race the
    # PR guards against: cleanup truncating raw data analyze is still reading).
    cleanup_upstream = tasks["cleanup_raw_setlistfm"].upstream_task_ids
    assert {"validate_raw", "transform", "analyze"} <= cleanup_upstream, cleanup_upstream
    print("cleanup_raw_setlistfm waits for validate_raw, transform AND analyze")

    # log_run also waits for analyze (it takes `analyzed` as an argument).
    assert "analyze" in tasks["log_run"].upstream_task_ids
    print("log_run depends on analyze")

    # trigger rules: cleanup and log_run run even if upstream failed;
    # analyze itself uses the default (only runs if transform succeeded).
    assert tasks["cleanup_raw_setlistfm"].trigger_rule == TriggerRule.ALL_DONE
    assert tasks["log_run"].trigger_rule == TriggerRule.ALL_DONE
    assert tasks["analyze"].trigger_rule == TriggerRule.ALL_SUCCESS
    print("trigger rules: cleanup_raw_setlistfm=ALL_DONE, log_run=ALL_DONE, analyze=ALL_SUCCESS (default)")

    print("\nALL STRUCTURAL CHECKS PASSED")


if __name__ == "__main__":
    main()
