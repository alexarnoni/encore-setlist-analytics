"""DB-level checks of the spec-03 dbt models and survival module against the
independent oracle. They need the isolated spec-03 database with the synthetic
histories loaded and the models built, so they only run on request:

    source scripts/spec03/env.sh && s3hostenv
    SPEC03_DB_TESTS=1 PYTHONPATH=src python -m pytest tests/spec03 -q
"""

import os

import pytest

from tests.support.db import assert_spec03_database, load_pools
from tests.support.histories import all_histories


def pytest_collection_modifyitems(config, items):
    if os.environ.get("SPEC03_DB_TESTS") == "1":
        return
    skip = pytest.mark.skip(reason="set SPEC03_DB_TESTS=1 (isolated spec-03 database, see conftest)")
    for item in items:
        if "tests/spec03" in item.nodeid.replace("\\", "/"):
            item.add_marker(skip)


@pytest.fixture(scope="session")
def conn():
    from encore.db import get_connection

    assert_spec03_database()
    connection = get_connection()
    yield connection
    connection.close()


@pytest.fixture(scope="session")
def pools_and_catalog(conn):
    return load_pools(conn)


@pytest.fixture(scope="session")
def shows(pools_and_catalog):
    return all_histories(pools_and_catalog[0])


@pytest.fixture(scope="session")
def catalog(pools_and_catalog):
    return pools_and_catalog[1]


def fetch(conn, sql, params=None):
    with conn.cursor() as cur:
        cur.execute(sql, params or ())
        return cur.fetchall()
