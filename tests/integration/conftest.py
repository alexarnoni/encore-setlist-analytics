"""Shared fixtures for the integration test suite.

These tests need a real PostgreSQL instance — start postgres-test first
(see README.md "Integration tests"):

    docker compose -f infra/docker-compose.yml --env-file .env \
        --profile test up -d postgres-test

Tests here skip automatically if postgres-test isn't reachable, so the
main `pytest` run (tests/, which does not include tests/integration/ by
default per pytest.ini) never depends on Docker.
"""

from __future__ import annotations

import os

import psycopg2
import pytest

from encore.db import ensure_schemas


@pytest.fixture(scope="session")
def _pg_session_connection():
    # Session-scoped so the connection attempt (and its timeout, if
    # postgres-test isn't running) happens once for the whole run, not
    # once per test — the difference between an instant `pytest
    # tests/integration` and one that takes ~4s/test to skip everything.
    try:
        conn = psycopg2.connect(
            host=os.environ.get("POSTGRES_TEST_HOST", "localhost"),
            port=os.environ.get("POSTGRES_TEST_PORT", "5436"),
            dbname=os.environ.get("POSTGRES_TEST_DB", "encore_test"),
            user=os.environ.get("POSTGRES_TEST_USER") or os.environ.get("POSTGRES_USER", "airflow"),
            password=os.environ.get("POSTGRES_TEST_PASSWORD") or os.environ.get("POSTGRES_PASSWORD", ""),
            connect_timeout=3,
        )
    except psycopg2.OperationalError as exc:
        pytest.skip(f"postgres-test not reachable at 127.0.0.1:5436 ({exc})")
        return

    ensure_schemas(conn)
    yield conn
    conn.close()


@pytest.fixture()
def pg_connection(_pg_session_connection):
    return _pg_session_connection
