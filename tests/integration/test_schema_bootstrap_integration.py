"""Integration coverage for encore.db against a real PostgreSQL (spec-01
item 6): ensure_schemas() is idempotent against an already-initialized
database, not just against a fresh one.
"""

from __future__ import annotations

from encore.db import SCHEMAS, ensure_schemas


def test_ensure_schemas_is_idempotent_against_a_real_database(pg_connection):
    ensure_schemas(pg_connection)  # pg_connection fixture already ran this once
    ensure_schemas(pg_connection)  # running it again must not raise

    with pg_connection.cursor() as cur:
        cur.execute(
            "SELECT schema_name FROM information_schema.schemata WHERE schema_name = ANY(%s)",
            (list(SCHEMAS),),
        )
        found = {row[0] for row in cur.fetchall()}

    assert found == set(SCHEMAS)
