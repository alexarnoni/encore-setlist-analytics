# Encore

Non-commercial data portfolio project analyzing how bands use their own
catalog in live shows over their careers. See
[docs/encore-projeto.md](docs/encore-projeto.md) for the full project
brief and [docs/context/](docs/context/) for product/tech/structure
context used to drive implementation.

> This README grows spec by spec. The sections below cover what
> spec-01 (infrastructure and ingestion) has built so far; see
> [docs/specs/spec-01-progress.md](docs/specs/spec-01-progress.md) for
> the detailed task-by-task log.

## Running locally

```bash
cp .env.example .env   # fill in real values, see comments in the file
docker compose -f infra/docker-compose.yml --env-file .env up
```

The `--env-file .env` is required, not optional: Docker Compose resolves
the `${VAR}` placeholders in `infra/docker-compose.yml` (including the
required-variable checks) against a `.env` file in the compose file's own
directory (`infra/`) by default, not against the repo root where this
project's `.env` actually lives. Without `--env-file .env`, `docker
compose up` fails immediately with "variable is missing a value" even
though `.env` exists one level up. Run every `docker compose` command
for this project the same way, e.g.:

```bash
docker compose -f infra/docker-compose.yml --env-file .env ps
docker compose -f infra/docker-compose.yml --env-file .env down
```

## Database schema bootstrap

The shared PostgreSQL instance holds two databases: `airflow` (Airflow's
own metadata) and `encore` (this project's data). Inside `encore`, six
schemas exist: `raw_setlistfm`, `raw_musicbrainz`, `staging`,
`intermediate`, `analytics`, `ops` (see
[docs/context/structure.md](docs/context/structure.md) for what each one
holds).

Schema creation is idempotent (`CREATE SCHEMA IF NOT EXISTS`) and runs in
two ways:

1. **Automatically on first boot**, via
   [infra/postgres/init/](infra/postgres/init/) — these scripts only run
   when the `postgres-db-volume` is empty (standard Postgres image
   behavior), so they never touch an already-initialized database.
2. **On demand, against any existing database** — for example after
   restoring a volume that predates a schema, or if you ever need to
   re-run it manually:

   ```bash
   python -m encore.db
   ```

   This requires `POSTGRES_USER`, `POSTGRES_PASSWORD` and, outside the
   `airflow-*` containers, `POSTGRES_HOST`/`POSTGRES_PORT` pointing at the
   exposed port (`127.0.0.1:5435` locally) — see
   [.env.example](.env.example). From the host (not inside a container),
   also set `PYTHONPATH=src` so `python -m encore.db` can find the
   package:

   ```bash
   PYTHONPATH=src POSTGRES_HOST=localhost POSTGRES_PORT=5435 python -m encore.db
   ```

   Safe to run repeatedly — verified against a real PostgreSQL container:
   running it a second time against the schemas created by
   `infra/postgres/init/` on first boot produces no errors.

## Integration tests

Unit tests (`pytest`, no arguments) run against mocked HTTP and mocked
DB connections — no Docker required. `tests/integration/` instead runs
the same ingestion/ops code against a **real** PostgreSQL, to catch bugs
mocks can't (wrong SQL syntax, a broken foreign key, an upsert that
doesn't actually dedupe). It's excluded from the default `pytest` run
(see `pytest.ini`'s `norecursedirs`), so it needs to be invoked
explicitly, and it needs `postgres-test` running first:

```bash
docker compose -f infra/docker-compose.yml --env-file .env --profile test up -d postgres-test
PYTHONPATH=src python -m pytest tests/integration -v
docker compose -f infra/docker-compose.yml --env-file .env --profile test down
```

If `postgres-test` isn't running, every test in `tests/integration/`
skips (rather than erroring) — the connection attempt happens once per
session, so a skip run finishes in a few seconds, not minutes.
