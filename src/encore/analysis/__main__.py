"""Entry point for the survival analysis step: `python -m encore.analysis`.

Called by the `analyze` Airflow task (T10), after `transform`'s dbt run and
before `cleanup_raw_setlistfm` — raw setlist.fm data must still be there,
since `intermediate.int_show_song_sets` and `intermediate.int_performances`
are views over it. Any exception here is left to propagate: the caller (the
Airflow task) is responsible for turning it into a failed task.
"""

from __future__ import annotations

import logging

from encore.analysis.io import write_survival_marts
from encore.db import get_connection

logger = logging.getLogger(__name__)


def main() -> None:
    conn = get_connection()
    try:
        song_rows, curve_rows, summary_rows = write_survival_marts(conn)
        logger.info(
            "Survival marts written: %d song rows, %d curve rows, %d summary rows",
            song_rows, curve_rows, summary_rows,
        )
    finally:
        conn.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
