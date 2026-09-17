from unittest.mock import MagicMock

from encore.db import SCHEMAS, ensure_schemas


def test_ensure_schemas_creates_every_schema_idempotently():
    conn = MagicMock()
    cursor = conn.cursor.return_value.__enter__.return_value

    ensure_schemas(conn)

    executed = [call.args[0] for call in cursor.execute.call_args_list]

    assert len(executed) == len(SCHEMAS)
    for schema in SCHEMAS:
        assert any(schema in stmt for stmt in executed)
    assert all("CREATE SCHEMA IF NOT EXISTS" in stmt for stmt in executed)
    conn.commit.assert_called_once()


def test_schema_list_matches_structure_md():
    # docs/context/structure.md lists these six schemas inside `encore`.
    assert SCHEMAS == (
        "raw_setlistfm",
        "raw_musicbrainz",
        "staging",
        "intermediate",
        "analytics",
        "ops",
    )
