"""Spec-01 R8.3: fail if any table in `analytics` has a `setlist_id` column.

`analytics` only ever holds aggregated marts (structure.md: "Nothing
under analytics may contain per-show or per-setlist rows derived from
setlist.fm"). A `setlist_id` column would be the clearest possible sign
that raw per-setlist rows leaked into a persisted, published schema.
"""

from __future__ import annotations


def _setlist_id_columns(conn) -> list[tuple[str, str]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE table_schema = 'analytics' AND column_name = 'setlist_id'
            """
        )
        return cur.fetchall()


def test_no_analytics_table_has_a_setlist_id_column(pg_connection):
    # analytics has no tables yet (marts land in spec 02) — this passes
    # vacuously today and becomes a real guard once tables exist.
    offending = _setlist_id_columns(pg_connection)
    assert offending == [], f"analytics tables with a setlist_id column: {offending}"


def test_guard_actually_detects_a_violation(pg_connection):
    # Proves the query above isn't vacuously trivial: plant a violation,
    # confirm it's caught, then clean up regardless of the outcome.
    with pg_connection.cursor() as cur:
        cur.execute("CREATE TABLE analytics._guard_test_violation (setlist_id TEXT)")
    pg_connection.commit()

    try:
        offending = _setlist_id_columns(pg_connection)
        assert offending == [("_guard_test_violation", "setlist_id")]
    finally:
        with pg_connection.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS analytics._guard_test_violation")
        pg_connection.commit()
