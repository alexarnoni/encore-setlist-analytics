"""Diagnostic lists for the end of the transform task, written to the log only.

After `dbt test` the pipeline still holds this run's setlist data, and it is
deleted right after (raw_setlistfm is ephemeral). This is the only moment to
see which song titles are behind the numbers, so per band it logs:

* a summary: performances, matched, matched with a release year, matched
  without one, unmatched;
* the top catalog songs that have NO release year (with their catalog_source
  and performance count): they match but cannot enter the repertoire age;
* the top unmatched setlist titles with their performance counts.

Nothing here is persisted. The connection is read-only, no temp table is
created, and the result goes through `logging` into the Airflow task log
(never into a table). Scope is the same as the marts: performances whose show
has a known year.
"""

from __future__ import annotations

import logging
from typing import Any

from encore.db import get_connection

logger = logging.getLogger(__name__)

TOP_N = 20
MAX_TITLE_LENGTH = 80
_PREFIX = "[report]"

SUMMARY_SQL = """
select
    band,
    count(*) as performances,
    count(*) filter (where is_matched) as matched,
    count(*) filter (where is_matched and release_year is not null) as aged,
    count(*) filter (where is_matched and release_year is null) as matched_without_year,
    count(*) filter (where not is_matched) as unmatched
from intermediate.int_performances
where show_year is not null
group by band
order by band
"""

UNDATED_SONGS_SQL = """
with counted as (
    select
        band,
        title_normalized,
        song_title,
        catalog_source,
        count(*) as performances
    from intermediate.int_performances
    where is_matched
      and release_year is null
      and show_year is not null
    group by band, title_normalized, song_title, catalog_source
),
ranked as (
    select
        *,
        row_number() over (partition by band order by performances desc, song_title) as rank
    from counted
)
select band, rank, performances, catalog_source, song_title
from ranked
where rank <= %(top_n)s
order by band, rank
"""

UNMATCHED_TITLES_SQL = """
with counted as (
    select
        band,
        title_normalized,
        mode() within group (order by song_name_raw) as example_name,
        count(*) as performances
    from intermediate.int_performances
    where not is_matched
      and show_year is not null
    group by band, title_normalized
),
ranked as (
    select
        *,
        row_number() over (partition by band order by performances desc, example_name) as rank
    from counted
)
select band, rank, performances, example_name
from ranked
where rank <= %(top_n)s
order by band, rank
"""


def _fetch(conn: Any, sql: str, params: dict | None = None) -> list[tuple]:
    with conn.cursor() as cur:
        cur.execute(sql, params or {})
        return cur.fetchall()


def _clean(title: object) -> str:
    """One line, no control characters, bounded length: safe for a log line."""
    text = " ".join(str(title if title is not None else "").split())
    if not text:
        return "(empty)"
    if len(text) > MAX_TITLE_LENGTH:
        text = text[: MAX_TITLE_LENGTH - 1] + "…"
    return text


def _share(part: int, whole: int) -> str:
    return f"{100 * part / whole:.2f}%" if whole else "n/a"


def build_report_lines(conn: Any, top_n: int = TOP_N) -> list[str]:
    """Return the report as log lines, one band after another."""
    summary = _fetch(conn, SUMMARY_SQL)
    undated = _fetch(conn, UNDATED_SONGS_SQL, {"top_n": top_n})
    unmatched = _fetch(conn, UNMATCHED_TITLES_SQL, {"top_n": top_n})

    undated_by_band: dict[str, list[tuple]] = {}
    for band, rank, performances, source, title in undated:
        undated_by_band.setdefault(band, []).append((rank, performances, source, title))
    unmatched_by_band: dict[str, list[tuple]] = {}
    for band, rank, performances, name in unmatched:
        unmatched_by_band.setdefault(band, []).append((rank, performances, name))

    lines = [
        f"{_PREFIX} Diagnostic lists for this run (task log only, never stored). "
        f"Scope: performances with a known show year, like the marts."
    ]
    for band, performances, matched, aged, without_year, unmatched_count in summary:
        lines.append(
            f"{_PREFIX} {band}: {performances} performances | {matched} matched "
            f"({_share(matched, performances)}) | {aged} with a release year "
            f"({_share(aged, performances)} of performances, {_share(aged, matched)} of matched) | "
            f"{without_year} matched without a release year ({_share(without_year, performances)}) | "
            f"{unmatched_count} unmatched ({_share(unmatched_count, performances)})"
        )
        lines.append(f"{_PREFIX}   {band}: top {top_n} catalog songs WITHOUT a release year")
        rows = undated_by_band.get(band, [])
        if not rows:
            lines.append(f"{_PREFIX}     (none)")
        for rank, count, source, title in rows:
            lines.append(f"{_PREFIX}     {rank:>2}. {count:>6}  {source:<9}  {_clean(title)}")
        lines.append(f"{_PREFIX}   {band}: top {top_n} UNMATCHED setlist titles")
        rows = unmatched_by_band.get(band, [])
        if not rows:
            lines.append(f"{_PREFIX}     (none)")
        for rank, count, name in rows:
            lines.append(f"{_PREFIX}     {rank:>2}. {count:>6}  {_clean(name)}")
    if not summary:
        lines.append(f"{_PREFIX} int_performances is empty: nothing to report.")
    return lines


def log_transform_report(conn: Any = None, top_n: int = TOP_N) -> None:
    """
    Log the diagnostic lists. Never raises: a failure here must not fail a
    pipeline whose dbt steps succeeded, so it is logged as a warning.
    """
    owns_connection = conn is None
    try:
        if owns_connection:
            conn = get_connection()
        conn.set_session(readonly=True, autocommit=True)
        for line in build_report_lines(conn, top_n):
            logger.info("%s", line)
    except Exception:  # noqa: BLE001 - diagnostics are best effort
        logger.warning("%s could not build the diagnostic lists", _PREFIX, exc_info=True)
    finally:
        if owns_connection and conn is not None:
            conn.close()
