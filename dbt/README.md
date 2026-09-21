# Encore dbt project

Transforms the raw MusicBrainz and (ephemeral) setlist.fm data into
aggregated marts. Built up task by task in spec-02a — see
[docs/specs/spec-02a-progress.md](../docs/specs/spec-02a-progress.md)
for what exists so far and the decisions behind it.

## Layout and schemas

| Path | Schema (database `encore`) | Materialization |
|---|---|---|
| `models/staging/` | `staging` | view |
| `models/intermediate/` | `intermediate` | view |
| `models/analytics/` | `analytics` | **table** |
| `seeds/` | `staging` | table (dbt seeds) |

`models/staging/test_fixtures/` holds models that exist only to test
macros (literal inputs, no raw data). They build as ordinary staging
views; their tests live in `tests/`.

Views for staging/intermediate are deliberate: they read
`raw_setlistfm`, which is truncated at the end of every pipeline run, so
they break harmlessly once that data is gone instead of holding a stale
copy. Only `analytics` persists, and nothing there may contain per-show
or per-setlist rows (a singular test enforces that).

`macros/generate_schema_name.sql` makes the layer schemas exactly
`staging`/`intermediate`/`analytics`. Without it dbt would name them
`<profile schema>_<layer>`.

## Prerequisites

- The Docker stack running (`make up`), or at least `postgres`.
- The `unaccent` Postgres extension. It is created by
  `infra/postgres/init/03_create_unaccent_extension.sh` — but init
  scripts only run on an **empty** volume, so a database created before
  that script existed needs it once by hand, as a superuser:
  `CREATE EXTENSION IF NOT EXISTS unaccent;` (connected to `encore`).
  Every dbt run starts by checking it exists and fails with a clear
  message if not — it never tries to create it.
- Connection settings come from environment variables only
  (`profiles.yml` contains no literal credentials): `POSTGRES_HOST`,
  `POSTGRES_PORT`, `POSTGRES_USER`, `POSTGRES_PASSWORD`. The database is
  always `encore`.

## Running dbt locally

dbt is **not** installed in the project's Python venv. It lives in an
isolated venv inside the Airflow image (`/opt/dbt-venv`, see
`airflow/Dockerfile`) so its dependencies can't conflict with Airflow's.
To run it from your machine, use that image with this directory
mounted:

```bash
set -a; source .env; set +a      # exports POSTGRES_USER / POSTGRES_PASSWORD

dbt() {
  MSYS_NO_PATHCONV=1 docker run --rm \
    -v "$PWD/dbt:/opt/airflow/dbt" \
    --network infra_default \
    -e POSTGRES_HOST=postgres -e POSTGRES_PORT=5432 \
    -e POSTGRES_USER -e POSTGRES_PASSWORD \
    -e DBT_TARGET_PATH=/tmp/dbt-target -e DBT_LOG_PATH=/tmp/dbt-logs \
    -e DBT_SEND_ANONYMOUS_USAGE_STATS=false \
    --entrypoint /opt/dbt-venv/bin/dbt \
    encore-airflow:3.3.2 \
    "$@" --project-dir /opt/airflow/dbt --profiles-dir /opt/airflow/dbt
}

dbt debug     # connection check
dbt seed      # load dbt/seeds/*.csv
dbt run       # build models (add --select <model> for one)
dbt test
```

Notes on the invocation:

- `--network infra_default` is the network Compose creates for the
  `infra/` project; `POSTGRES_HOST=postgres` is the service name on it.
- `DBT_TARGET_PATH`/`DBT_LOG_PATH` point at `/tmp` inside the throwaway
  container. Without them dbt writes `target/` and `logs/` into the
  mounted `dbt/` directory, i.e. into your working tree. They are
  environment variables rather than `--target-path`/`--log-path` flags
  because not every subcommand accepts those flags (`dbt debug` doesn't).
- `DBT_SEND_ANONYMOUS_USAGE_STATS=false` also stops dbt from dropping a
  `.user.yml` (its anonymous-user id) next to `profiles.yml`.
- `MSYS_NO_PATHCONV=1` stops Git Bash on Windows from rewriting the
  `/opt/...` paths. It is harmless elsewhere.
- Rebuild the image (`docker compose -f infra/docker-compose.yml
  --env-file .env build`) if you change `airflow/Dockerfile`; the
  directory mount means model/macro/seed edits are picked up
  immediately, no rebuild needed.

## Running dbt inside Airflow

The `transform` task of `encore_pipeline` runs `dbt seed --full-refresh`,
`dbt run` and `dbt test`, in that order, using the copy of this directory baked into the
image (`/opt/airflow/dbt`, see `airflow/Dockerfile`). It executes after
`validate_raw` and before `cleanup_raw_setlistfm`, in the same DAG run, so
raw setlist.fm data is still there when dbt reads it. The code lives in
`src/encore/dbt_runner.py`; the image's `DBT_*` environment variables
select the project, profile, output paths and turn off colors, so the
task passes no flags.

- **Logs.** dbt's output is streamed line by line into the Airflow task
  log (each line prefixed `[dbt]`), so it is visible while the task runs.
- **Failure.** If any of the three commands exits non-zero, the task
  fails immediately with `AirflowFailException` (no retry — the same data
  would fail the same way) and the later steps do not run.
  `cleanup_raw_setlistfm` and `log_run` have `trigger_rule=all_done`, so
  they still run: raw data is deleted and the run is logged as `failed`.
- **Not transactional.** `dbt run` replaces the `analytics` tables before
  `dbt test` checks them. A failing test fails the pipeline but does not
  roll the new tables back.
- **Seeds run every time, with `--full-refresh`.** They are two tiny
  tables, so nothing is skipped when the CSVs are unchanged. A plain
  `dbt seed` only truncates and reloads an existing table and never adds
  a column, so after a seed gains a column it would report success and
  leave the old table shape in place. Full refresh drops and recreates
  the seed tables (and, through `CASCADE`, the views on top of them), so
  always follow it with a full `dbt run`, as the task does.
- **Image contents.** Because `dbt/` is copied into the image, rebuild it
  (`docker compose -f infra/docker-compose.yml --env-file .env up -d
  --build`) after changing a model, macro or seed for the DAG to see the
  change. The `docker run -v` function above mounts the directory instead,
  which is why it needs no rebuild.

### Do not use `airflow tasks test` on an unpaused DAG

`airflow tasks test` looks like it runs one task in isolation, but in
Airflow 3 it creates a temporary DagRun in the metadata database, and a
running scheduler executes the *real* tasks of that run — starting with
`truncate_raw_setlistfm_start` (which empties `raw_setlistfm`, including
any dev fixture) and `extract_musicbrainz` (which makes real MusicBrainz
requests). `encore_pipeline` is created paused (`docker-compose.yml`), so
keep it paused when testing tasks this way:

    docker exec infra-airflow-scheduler-1 airflow dags pause encore_pipeline

## Reviewing and fixing release dates

A song's release year is its **first official release year**: the earlier
of the reference album's year and the earliest MusicBrainz recording's
year. A wrong (too early) recording date therefore makes a song look
older than it is. `intermediate.int_song_release_date_audit` lists songs
whose recording is more than 2 years before the album; the warn-level test
`assert_song_recording_date_not_far_before_album` reports how many:

    select * from intermediate.int_song_release_date_audit;

To settle one, add a row to `seeds/seed_song_overrides.csv` with only
`band`, `canonical_song_title` and `first_release_year` (leave
`raw_song_name` and `album_title` blank), e.g.

    Oasis,,Let There Be Love,,2005

The year replaces the computed one, `release_year_fixed` becomes true and
the song leaves the audit list. Tests reject a malformed or implausible
year, two different years for one song, and a title that is not in that
band's catalog.

## Local development data

`raw_setlistfm` is ephemeral by data policy (see
[docs/context/product.md](../docs/context/product.md)) — the real
pipeline truncates it at the end of every run, so there's normally
nothing to develop dbt models against between runs.

For local dbt development, load a one-off, real (not synthetic) fixture
for a single band instead of running the full pipeline repeatedly:

```bash
PYTHONPATH=src POSTGRES_HOST=localhost POSTGRES_PORT=5435 \
    python scripts/load_dev_fixture.py
```

This loads Oasis into `raw_setlistfm` and `raw_musicbrainz` directly,
bypassing `encore_pipeline` and its `cleanup_raw_setlistfm` task, and
records the load timestamp in `ops.pipeline_runs` (`status =
'dev-fixture'`) so it's visible and distinguishable from a real run.

**This data is TEMPORARY.** Do not leave it in the database between
work sessions — truncate `raw_setlistfm` when you're done for the day:

```bash
PYTHONPATH=src POSTGRES_HOST=localhost POSTGRES_PORT=5435 python -c "
from encore.db import get_connection
from encore.ingestion.setlistfm import truncate_all
truncate_all(get_connection())
"
```

(`raw_musicbrainz` is persistent by design — see
[docs/context/structure.md](../docs/context/structure.md) — so it's
fine to leave the MusicBrainz half of the fixture in place.)
