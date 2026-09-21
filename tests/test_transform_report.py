import logging
import re
from unittest.mock import MagicMock

import pytest

from encore import transform_report
from encore.transform_report import (
    SUMMARY_SQL,
    UNDATED_SONGS_SQL,
    UNMATCHED_TITLES_SQL,
    _clean,
    build_report_lines,
    log_transform_report,
)


def _fake_fetch(monkeypatch, summary=(), undated=(), unmatched=()):
    """Make _fetch answer by query, and remember the parameters it got."""
    calls: dict = {}

    def fetch(conn, sql, params=None):
        if sql is SUMMARY_SQL:
            return list(summary)
        if sql is UNDATED_SONGS_SQL:
            calls["undated"] = params
            return list(undated)
        if sql is UNMATCHED_TITLES_SQL:
            calls["unmatched"] = params
            return list(unmatched)
        raise AssertionError("unexpected query")

    monkeypatch.setattr(transform_report, "_fetch", fetch)
    return calls


def test_queries_are_read_only():
    for sql in (SUMMARY_SQL, UNDATED_SONGS_SQL, UNMATCHED_TITLES_SQL):
        assert re.match(r"\s*(select|with)\b", sql, re.I)
        assert not re.search(r"\b(insert|update|delete|create|drop|truncate|alter|grant)\b", sql, re.I)


def test_clean_makes_one_bounded_line():
    assert _clean("  Wonder\nwall\t(live)  ") == "Wonder wall (live)"
    assert _clean("") == "(empty)"
    assert _clean(None) == "(empty)"
    long = _clean("x" * 500)
    assert len(long) == transform_report.MAX_TITLE_LENGTH and long.endswith("…")


def test_report_lists_songs_and_titles_per_band_with_counts(monkeypatch):
    calls = _fake_fetch(
        monkeypatch,
        summary=[("Metallica", 1000, 900, 800, 100, 100), ("Muse", 50, 12, 12, 0, 38)],
        undated=[
            ("Metallica", 1, 60, "recording", "Helpless (jam)"),
            ("Metallica", 2, 40, "recording", "Master of Puppet"),
        ],
        unmatched=[("Muse", 1, 30, "Some Demo"), ("Muse", 2, 8, "Another Demo")],
    )

    text = "\n".join(build_report_lines(conn=None, top_n=5))

    assert calls == {"undated": {"top_n": 5}, "unmatched": {"top_n": 5}}
    assert "Metallica: 1000 performances | 900 matched (90.00%) | 800 with a release year" in text
    assert "100 matched without a release year (10.00%)" in text
    assert "top 5 catalog songs WITHOUT a release year" in text
    assert " 1.     60  recording  Helpless (jam)" in text
    assert " 2.     40  recording  Master of Puppet" in text
    assert "Muse: top 5 UNMATCHED setlist titles" in text
    assert " 1.     30  Some Demo" in text
    # Metallica has no unmatched titles in the fake data, Muse has no undated songs
    metallica, muse = text.split("Muse: 50 performances")
    assert "(none)" in muse.split("UNMATCHED")[0]
    assert "(none)" in metallica.split("UNMATCHED setlist titles")[1]


def test_report_says_so_when_there_is_nothing(monkeypatch):
    _fake_fetch(monkeypatch)

    assert "nothing to report" in "\n".join(build_report_lines(conn=None))


def test_report_handles_a_band_with_no_matched_performances(monkeypatch):
    _fake_fetch(monkeypatch, summary=[("Muse", 9, 0, 0, 0, 9)])

    text = "\n".join(build_report_lines(conn=None))

    assert "0 matched (0.00%)" in text
    assert "n/a of matched" in text


def test_log_writes_lines_through_logging_and_uses_a_read_only_session(monkeypatch, caplog):
    _fake_fetch(monkeypatch, summary=[("Oasis", 10, 9, 8, 1, 1)])
    conn = MagicMock()

    with caplog.at_level(logging.INFO, logger="encore.transform_report"):
        log_transform_report(conn=conn)

    conn.set_session.assert_called_once_with(readonly=True, autocommit=True)
    assert any("Oasis: 10 performances" in r.getMessage() for r in caplog.records)
    conn.close.assert_not_called()  # a connection passed in stays the caller's


def test_log_opens_and_closes_its_own_connection(monkeypatch):
    _fake_fetch(monkeypatch)
    conn = MagicMock()
    monkeypatch.setattr(transform_report, "get_connection", lambda: conn)

    log_transform_report()

    conn.close.assert_called_once()


def test_log_never_raises_when_the_database_is_unavailable(monkeypatch, caplog):
    def boom():
        raise RuntimeError("no database")

    monkeypatch.setattr(transform_report, "get_connection", boom)

    with caplog.at_level(logging.WARNING, logger="encore.transform_report"):
        log_transform_report()  # must not raise

    assert any("could not build the diagnostic lists" in r.getMessage() for r in caplog.records)


def test_log_never_raises_when_a_query_fails(monkeypatch):
    def failing_fetch(*args, **kwargs):
        raise RuntimeError("bad query")

    monkeypatch.setattr(transform_report, "_fetch", failing_fetch)
    conn = MagicMock()

    log_transform_report(conn=conn)  # must not raise
