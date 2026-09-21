"""PostgreSQL connection helper and idempotent schema bootstrap.

Connects to the single `encore` database (docs/context/structure.md)
inside the shared PostgreSQL instance. Airflow's own metadata database
name is configurable via POSTGRES_DB, but this module always targets
`encore` explicitly — the two are different databases in the same
instance.
"""

from __future__ import annotations

import os

import psycopg2
from psycopg2.extensions import connection as Connection

DATABASE_NAME = "encore"

# Fixed, internal identifiers (never derived from user input), so plain
# string interpolation into the CREATE SCHEMA statement is safe here.
SCHEMAS = (
    "raw_setlistfm",
    "raw_musicbrainz",
    "staging",
    "intermediate",
    "analytics",
    "ops",
)


def get_connection() -> Connection:
    """Open a connection to the `encore` database using POSTGRES_* env vars."""
    return psycopg2.connect(
        host=os.environ.get("POSTGRES_HOST", "postgres"),
        port=os.environ.get("POSTGRES_PORT", "5432"),
        dbname=DATABASE_NAME,
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
    )


def ensure_schemas(conn: Connection) -> None:
    """
    Create every schema in SCHEMAS if it does not already exist.

    Idempotent: safe to run against a fresh database or one that already
    has some or all of the schemas (spec-01 adjustment 5). This is the
    same operation infra/postgres/init/02_create_schemas.sh runs on first
    container boot, exposed here so it can also run on demand against an
    existing database (e.g. after a manual schema drop, or in an
    environment where the init scripts already ran once and won't run
    again).
    """
    with conn.cursor() as cur:
        for schema in SCHEMAS:
            cur.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
    conn.commit()


if __name__ == "__main__":
    connection = get_connection()
    try:
        ensure_schemas(connection)
        print(f"Schemas ensured: {', '.join(SCHEMAS)}")
    finally:
        connection.close()
