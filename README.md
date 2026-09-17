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
   [.env.example](.env.example). Safe to run repeatedly.
