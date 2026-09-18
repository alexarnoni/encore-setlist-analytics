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

Not wired up yet — the `transform` task in `encore_pipeline` is still a
placeholder. Spec-02a items 19–20 copy this directory into the image
(`/opt/airflow/dbt`) and replace the placeholder with `dbt seed`,
`dbt run` and `dbt test`, run before `cleanup_raw_setlistfm` in the same
DAG run. This section will describe the final behaviour once that lands.

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
