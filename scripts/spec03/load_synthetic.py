"""Load the spec-03 synthetic histories into raw_setlistfm of the isolated
spec-03 database (never the real one: tests.support.db refuses any other host).

Needs the catalog built first (`s3dbt seed --full-refresh` and `s3dbt run`),
because the song names come from the real MusicBrainz catalog copy.

    source scripts/spec03/env.sh
    s3py /opt/airflow/scripts/spec03/load_synthetic.py
"""

from __future__ import annotations

from encore.db import get_connection
from tests.support.db import assert_spec03_database, insert_histories, load_pools, reset_raw_setlistfm
from tests.support.histories import all_histories


def main() -> None:
    assert_spec03_database()
    conn = get_connection()
    try:
        pools, _ = load_pools(conn)
        shows = all_histories(pools)
        reset_raw_setlistfm(conn)
        setlists, entries = insert_histories(conn, shows)
    finally:
        conn.close()
    bands = sorted({s.band for s in shows})
    print(f"loaded {setlists} synthetic setlists / {entries} entries for {', '.join(bands)}")


if __name__ == "__main__":
    main()
