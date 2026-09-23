"""T2: the marts loader is analytics-only and read-only; the fixture mirrors the real columns."""

from datetime import date
from pathlib import Path

import pytest
import yaml

from encore.site import marts
from tests.site.fixtures import BANDS, fake_marts

DBT_DIR = Path(__file__).resolve().parents[2] / "dbt" / "models" / "analytics"


def _documented_columns() -> dict[str, list[str]]:
    """Column lists of every analytics mart, from the dbt yml files (the source of truth)."""
    cols: dict[str, list[str]] = {}
    for m in yaml.safe_load((DBT_DIR / "schema.yml").read_text(encoding="utf8"))["models"]:
        cols[m["name"]] = [c["name"] for c in m["columns"]]
    for src in yaml.safe_load((DBT_DIR / "_survival_sources.yml").read_text(encoding="utf8"))["sources"]:
        for t in src["tables"]:
            cols[t["name"]] = [c["name"] for c in t["columns"]]
    return cols


class FakeCursor:
    def __init__(self, log: list[str]) -> None:
        self.log = log
        self.description = [type("C", (), {"name": n})() for n in ("band", "show_year", "computed_at")]

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        return None

    def execute(self, sql: str) -> None:
        self.log.append(sql)

    def fetchall(self):
        return [("Muse", 2001, date(2026, 9, 23))]


class FakeConn:
    def __init__(self) -> None:
        self.sql: list[str] = []

    def cursor(self) -> FakeCursor:
        return FakeCursor(self.sql)


def test_fixture_columns_match_dbt_documentation() -> None:
    documented = _documented_columns()
    marts_ = fake_marts()
    assert set(marts_) == set(marts.MART_TABLES)
    for table, df in marts_.items():
        assert list(df.columns) == documented[table], table


def test_fixture_covers_every_band_and_window() -> None:
    summary = fake_marts()["mart_survival_summary"]
    assert sorted(summary["band"].unique()) == sorted(BANDS)
    assert sorted(summary["n_window"].unique()) == [25, 50, 100]


def test_allowlist_excludes_song_level_and_other_schemas() -> None:
    assert "mart_song_survival" not in marts.MART_TABLES
    conn = FakeConn()
    for bad in ("mart_song_survival", "raw_setlistfm.setlists", "mart_repertoire_age; DROP TABLE x"):
        with pytest.raises(ValueError):
            marts.read_mart(conn, bad)
    assert conn.sql == []  # refused before any SQL is issued


def test_read_mart_queries_analytics_schema_only() -> None:
    conn = FakeConn()
    df = marts.read_mart(conn, "mart_match_quality")
    assert conn.sql == ["SELECT * FROM analytics.mart_match_quality"]
    assert list(df["band"]) == ["Muse"]


def test_connect_sets_read_only_session(monkeypatch) -> None:
    calls: dict = {}

    class C:
        def set_session(self, **kw) -> None:
            calls.update(kw)

    monkeypatch.setenv("POSTGRES_USER", "u")
    monkeypatch.setenv("POSTGRES_PASSWORD", "p")
    monkeypatch.setattr(marts.psycopg2, "connect", lambda **kw: (calls.update(connect=kw), C())[1])
    marts.connect()
    assert calls["readonly"] is True
    assert calls["connect"]["dbname"] == "encore"
    assert calls["connect"]["host"] == "127.0.0.1" and calls["connect"]["port"] == 5435


def test_data_as_of_is_latest_computed_at() -> None:
    assert marts.data_as_of(fake_marts()) == date(2026, 9, 23)
    with pytest.raises(ValueError):
        marts.data_as_of({})
