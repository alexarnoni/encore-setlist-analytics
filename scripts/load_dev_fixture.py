"""One-off dev fixture loader (spec-02a item 1).

Loads real Oasis data into raw_setlistfm and raw_musicbrainz directly —
bypassing encore_pipeline and its cleanup_raw_setlistfm task — so dbt
staging models have stable real data to develop against without
spending API quota on every iteration.

This data is TEMPORARY. `raw_setlistfm` is meant to be ephemeral (see
docs/context/product.md); do not leave this fixture in the database
between work sessions. Truncate it when you're done for the day:

    PYTHONPATH=src POSTGRES_HOST=localhost POSTGRES_PORT=5435 \
        python -c "from encore.db import get_connection; \
        from encore.ingestion.setlistfm import truncate_all; \
        truncate_all(get_connection())"

Usage:
    PYTHONPATH=src POSTGRES_HOST=localhost POSTGRES_PORT=5435 \
        python scripts/load_dev_fixture.py
"""

from __future__ import annotations

from datetime import datetime, timezone

from encore import ops
from encore.clients._http import get_counters, reset_counters
from encore.clients.musicbrainz import MusicBrainzClient
from encore.clients.setlistfm import SetlistFmClient
from encore.config import load_bands
from encore.db import ensure_schemas, get_connection
from encore.ingestion import musicbrainz as mb_ingestion
from encore.ingestion import setlistfm as sf_ingestion

BAND_NAME = "Oasis"


def main() -> None:
    band = next(b for b in load_bands() if b.name == BAND_NAME)

    conn = get_connection()
    ensure_schemas(conn)
    sf_ingestion.ensure_tables(conn)
    mb_ingestion.ensure_tables(conn)
    ops.ensure_tables(conn)

    reset_counters()
    started_at = datetime.now(timezone.utc)

    sf_summary = sf_ingestion.extract_band(SetlistFmClient(), conn, band, run_id="dev-fixture")
    # Default 30-day freshness threshold: MusicBrainz data from an
    # earlier real run (spec-01 item 25) is likely still fresh, so this
    # naturally skips re-fetching it instead of spending quota again.
    mb_summary = mb_ingestion.extract_band(MusicBrainzClient(), conn, band)

    finished_at = datetime.now(timezone.utc)
    counters = get_counters()

    # Recorded in ops.pipeline_runs with status="dev-fixture" (distinct
    # from "success"/"failed") so:
    # - the load timestamp is visible to anyone querying ops later, and
    # - check_api_budget's daily sum still counts these real requests
    #   (they did consume quota), but
    #   estimate_next_run_setlistfm_cost's "last successful run" query
    #   (status='success') ignores this row, so it never skews the
    #   estimate used for a real run's budget check.
    ops.log_run(
        conn,
        run_id=f"dev-fixture-{BAND_NAME.lower()}-{started_at:%Y%m%dT%H%M%S}",
        started_at=started_at,
        finished_at=finished_at,
        status="dev-fixture",
        setlistfm_requests=counters.get("setlistfm", 0),
        musicbrainz_requests=counters.get("musicbrainz", 0),
        setlists_per_band={BAND_NAME: sf_summary["setlists"]},
        error_message=None,
    )

    print(f"setlist.fm: {sf_summary}")
    print(f"MusicBrainz: {mb_summary}")
    print(
        "\nReminder: this is TEMPORARY dev data in raw_setlistfm/raw_musicbrainz. "
        "Do not leave it in the database between work sessions — see this "
        "file's docstring or dbt/README.md for how to truncate it."
    )

    conn.close()


if __name__ == "__main__":
    main()
