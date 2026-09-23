"""Read-only access to the `analytics` marts the site is built from.

The generator may read nothing but these tables (docs/specs/spec-04-site.md,
working rules): the table name is checked against an allowlist before any SQL
is built, the schema is fixed to `analytics`, and the session is read-only.
`mart_song_survival` is deliberately not listed: no page needs song-level rows.
"""

from __future__ import annotations

import logging
import os
from datetime import date

import pandas as pd
import psycopg2

logger = logging.getLogger(__name__)

SCHEMA = "analytics"

MART_TABLES: tuple[str, ...] = (
    "mart_repertoire_age",
    "mart_band_rotation_by_year",
    "mart_tour_rotation",
    "mart_match_quality",
    "mart_survival_curves",
    "mart_survival_summary",
)

# Columns that stay text; every other column except computed_at is numeric.
TEXT_COLUMNS = frozenset({"band", "album", "tour_name"})
RUN_COLUMN = "computed_at"


def connect():
    """Open a read-only connection to `encore` (host defaults: 127.0.0.1:5435).

    ENCORE_DB_HOST / ENCORE_DB_PORT override the address, as in the notebooks.
    """
    conn = psycopg2.connect(
        host=os.environ.get("ENCORE_DB_HOST", "127.0.0.1"),
        port=int(os.environ.get("ENCORE_DB_PORT", "5435")),
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        dbname="encore",
    )
    conn.set_session(readonly=True)
    return conn


def read_mart(conn, table: str) -> pd.DataFrame:
    """Read one allowlisted mart; numeric columns come back as plain numbers."""
    if table not in MART_TABLES:
        raise ValueError(f"{table!r} is not an allowed analytics table")
    with conn.cursor() as cur:
        # `table` was validated against MART_TABLES above; identifiers cannot be bound.
        cur.execute(f"SELECT * FROM {SCHEMA}.{table}")
        columns = [c.name for c in cur.description]
        df = pd.DataFrame(cur.fetchall(), columns=columns)
    numeric = [c for c in df.columns if c not in TEXT_COLUMNS and c != RUN_COLUMN]
    df[numeric] = df[numeric].apply(pd.to_numeric)
    logger.info("Read %s.%s: %d rows", SCHEMA, table, len(df))
    return df


def load_all(conn=None) -> dict[str, pd.DataFrame]:
    """Read every allowlisted mart. Opens (and closes) a connection if none is given."""
    own = conn is None
    if own:
        conn = connect()
    try:
        return {table: read_mart(conn, table) for table in MART_TABLES}
    finally:
        if own:
            conn.close()


def data_as_of(marts: dict[str, pd.DataFrame]) -> date:
    """Pipeline run date the data came from: the latest `computed_at` across the marts."""
    stamps = [m[RUN_COLUMN].max() for m in marts.values() if len(m) and RUN_COLUMN in m]
    if not stamps:
        raise ValueError("no mart has a computed_at value; cannot date the data")
    return pd.Timestamp(max(stamps)).date()
