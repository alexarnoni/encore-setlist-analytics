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
`validate_raw` and before `analyze`, in the same DAG run, so
raw setlist.fm data is still there when dbt reads it. The code lives in
`src/encore/dbt_runner.py`; the image's `DBT_*` environment variables
select the project, profile, output paths and turn off colors, so the
task passes no flags.

`transform`'s `dbt run`/`dbt test` **exclude** everything tagged
`survival` (`--exclude tag:survival`): the survival marts
(`mart_song_survival`, `mart_survival_curves`, `mart_survival_summary`)
are not dbt models — they are written directly by the `analyze` task
(`src/encore/analysis`, see below) using `lifelines`, which dbt-postgres
cannot run. The `survival` tag exists on their dbt-side sources/tests
(`dbt/models/analytics/survival_sources.yml`,
`dbt/tests/assert_survival_*.sql`) so `dbt test` still validates them, just
in a separate, later invocation, after `analyze` has written them.

## Running the `analyze` task

`analyze` runs between `transform` and `cleanup_raw_setlistfm`, still
inside the window where raw setlist.fm data exists (`int_show_song_sets`
and eligibility both read through it). It is plain Python, not dbt:
`src/encore/analysis/__main__.py` reads the show/song sets and song
attributes needed for survival, computes duration/event/censoring for
N = 25/50/100 (`src/encore/analysis/survival.py`, see
[`docs/methodology.md`](../docs/methodology.md) for the exact convention),
fits Kaplan-Meier curves per band and per band + album with `lifelines`,
and writes `mart_song_survival`, `mart_survival_curves` and
`mart_survival_summary` in one transaction (idempotent, atomic — a
mid-write failure leaves the previous content in place). Afterward,
`dbt test --select tag:survival` runs to validate the marts it just wrote
(reconciliation against `int_performances`, probability bounds, grain
uniqueness). If `analyze` fails, the task fails immediately (no retry, same
data would fail the same way) and `cleanup_raw_setlistfm`/`log_run` still
run (`trigger_rule=all_done`), same as a `transform` failure.

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
- **Image contents.** `dbt/` is copied into the image, and that copy is what
  runs in production. After changing a model, macro or seed, either rebuild
  (`make build`, which also bakes the commit hash) or, **for local development
  only**, start the stack with `make up-dev`: it bind-mounts `./dbt` read-only
  over `/opt/airflow/dbt`
  ([`infra/docker-compose.dev.yml`](../infra/docker-compose.dev.yml)), so the
  next transform run sees your edits with no rebuild. A stack started with
  plain `make up` uses the baked copy, and a stale image is an easy mistake
  (it once ran the previous project's tests without anyone noticing): check
  the version line below. The `docker run -v` function above mounts the
  directory the same way.
- **Which dbt project ran.** The first log line of every transform is
  `dbt project: commit=<hash> content_sha=<hash> dir=...`. `commit` is the last
  commit that touched `dbt/`, baked in at build time (`unknown` if the image
  was built without it; `<hash>-dirty` means uncommitted changes at build/up
  time). `content_sha` is a hash of the actual files, so it is the one to
  trust with the dev mount, where files may have changed since the stack
  started. To compare with the image, run the same function without the
  mount; equal `content_sha` means equal project.

### Do not use `airflow tasks test` on an unpaused DAG

`airflow tasks test` looks like it runs one task in isolation, but in
Airflow 3 it creates a temporary DagRun in the metadata database, and a
running scheduler executes the *real* tasks of that run — starting with
`truncate_raw_setlistfm_start` (which empties `raw_setlistfm`, including
any dev fixture) and `extract_musicbrainz` (which makes real MusicBrainz
requests). `encore_pipeline` is created paused (`docker-compose.yml`), so
keep it paused when testing tasks this way:

    docker exec infra-airflow-scheduler-1 airflow dags pause encore_pipeline

## End-of-run diagnostic lists (task log only)

After `dbt test` (pass or fail; skipped if `seed` or `run` failed) the
`transform` task logs, per band, a summary and two lists, then the raw data
is deleted. This is the only time the titles behind the numbers are
available. Lines start with `[report]`; the code is
`src/encore/transform_report.py`.

- summary: performances, matched, matched *with* a release year, matched
  *without* one, unmatched (counts and shares);
- the top 20 catalog songs with **no release year**, with performance count
  and `catalog_source`;
- the top 20 **unmatched** setlist titles, with performance counts.

Scope is the marts' (performances with a known show year). It reads through
a read-only session, creates nothing, writes nothing to any table, and never
fails the task (a problem is logged as a warning).

**Where it ends up.** Only in the task log. Task logs are files in the
`airflow-logs` volume and are removed by the `log_cleanup` DAG once older than
**7 days** (`MAX_LOG_AGE_DAYS` in `src/encore/log_cleanup.py`; it was 14).
That DAG is created active, not paused (`is_paused_upon_creation=False`), so
the retention applies on the VM too without anyone unpausing it; on a
machine where the DAG already existed paused, unpause it once:
`airflow dags unpause log_cleanup`. When a run is started with
`airflow dags test`, the output goes to the terminal instead; redirect it to
a file outside the repository and delete it after reading.

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

## Reconciliation test (runs inside every pipeline run)

`assert_marts_reconcile_with_int_performances` checks, per band, that the
performances (and matched performances) summed over `mart_repertoire_age`
and over `mart_match_quality` equal the rows of `int_performances`. Raw
setlist.fm data is deleted at the end of each run, so this is the only
in-run proof that nothing was lost or invented on the way to the marts. It
compares against the rows that have a known `show_year`, because the marts
leave undated performances out by design;
`assert_no_undated_performances_left_out_of_marts` (warn) reports how many
those are per band.

Because it needs raw data, **it fails by design outside a run**: once
`raw_setlistfm` has been truncated `int_performances` is empty while the
marts are still populated, so a `dbt test` on your machine between runs
shows this test red for every band. Do not "fix" it; it is green inside the
pipeline (and on freshly loaded dev data).

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
