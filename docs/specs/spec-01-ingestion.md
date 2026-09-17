# Spec 01: Infrastructure and ingestion

Read the context files in `docs/context/` before starting. This spec covers infrastructure, the ingestion layer and the Airflow DAG skeleton. dbt models, analysis and the frontend are out of scope.

## Goal

A reproducible pipeline that, on each run, loads the full setlist.fm history of the 7 bands into an ephemeral raw schema, keeps MusicBrainz discography data persistent, runs a placeholder transformation step, and deletes the raw setlist.fm data at the end.

## Requirements

### R1. Infrastructure
1. `infra/docker-compose.yml` with services: `postgres` (postgres:16), `airflow-init`, `airflow-webserver`, `airflow-scheduler`.
2. All images support linux/arm64. The Airflow image is built from `airflow/Dockerfile`, extending the official image and installing the project requirements and dbt-postgres.
3. Ports bound to 127.0.0.1 only, as defined in tech.md.
4. `infra/postgres/init/` creates the `encore` and `airflow` databases and the schemas `raw_setlistfm`, `raw_musicbrainz`, `staging`, `intermediate`, `analytics`, `ops`.
5. Named volumes for PostgreSQL data and Airflow logs.
6. Airflow log cleanup: logs older than 14 days are removed.
7. The same compose file works locally (x86) and on the VM (arm64).
8. `.env.example` lists every variable needed.

### R2. Band configuration
1. `config/bands.yaml` lists the 7 bands with name and MBID (MBIDs validated in Phase 0).
2. Ingestion reads bands only from this file.

### R3. API clients
1. Move `src/clients.py` into `src/encore/clients/` as `setlistfm.py` and `musicbrainz.py`, keeping rate limiting, backoff and request counters.
2. Remove the disk cache used in Phase 0 from the setlist.fm client. setlist.fm responses go straight to the raw schema.
3. The MusicBrainz client may keep a disk cache.
4. Clients log real request counts at the end of each task.

### R4. setlist.fm extraction (ephemeral)
1. For each band, paginate `/artist/{mbid}/setlists` until the last page.
2. Load into `raw_setlistfm` with two tables:
   - `setlists`: setlist id, artist MBID, event date, tour name, venue name, city, country, setlist.fm URL, run id, loaded at.
   - `setlist_entries`: setlist id, song name as returned, position, set index, is_encore, is_cover, cover artist, is_tape, run id.
3. Store the raw JSON only if needed for debugging, in the same schema, and truncate it with the rest.
4. Abort the run if the day's request budget would exceed 1,300 requests (safety margin).

### R5. MusicBrainz extraction (persistent)
1. Studio albums (release-groups of type album without secondary types).
2. Representative release per album: most frequent track count among official releases, earliest date, tie-break GB > US > XW.
3. Tracks of the representative release, with recording MBID and title.
4. All recordings of each band with first-release-date.
5. Load into `raw_musicbrainz` with upsert semantics (no duplicates across runs).
6. MusicBrainz extraction can be skipped when data is younger than 30 days (configurable).

### R6. Airflow DAG `encore_pipeline`
Tasks, in order:
1. `check_api_budget`
2. `extract_musicbrainz`
3. `extract_setlistfm` (one mapped task per band, run sequentially to respect the rate limit)
4. `validate_raw` (row counts per band, % of setlists with at least one song, fails if a band returns zero setlists)
5. `transform` (placeholder task that logs "dbt run pending spec 02")
6. `cleanup_raw_setlistfm` (truncates every table in `raw_setlistfm`)
7. `log_run` (writes to `ops.pipeline_runs`)

Rules:
- `cleanup_raw_setlistfm` runs with trigger rule `all_done`, so raw data is deleted even when earlier tasks fail.
- Schedule: monthly. Manual trigger allowed.
- `max_active_runs=1`, no catchup.

### R7. Run log
`ops.pipeline_runs`: run id, started at, finished at, status, setlist.fm requests, MusicBrainz requests, setlists loaded per band (JSON), error message.

### R8. Tests
1. Unit tests for the clients with mocked HTTP (pagination, 429 retry, request counter).
2. Unit test for the representative release selection.
3. A test that fails if any table in `analytics` has a column named `setlist_id`.

### R9. Documentation
`README.md` with: project summary, architecture diagram (Mermaid), data policy, how to run locally, how to deploy on the VM, and the setlist.fm attribution.

## Acceptance criteria

- `docker compose up` brings everything up locally with no manual steps besides filling `.env`.
- Triggering the DAG loads all 7 bands, then leaves `raw_setlistfm` empty.
- `raw_musicbrainz` keeps its data between runs without duplicates.
- A failed run still ends with `raw_setlistfm` empty.
- `ops.pipeline_runs` shows request counts below 1,300 for setlist.fm.
- No port is bound to 0.0.0.0.
- Tests pass.

## Out of scope

- dbt models (spec 02)
- KPIs and survival analysis (spec 03)
- API and frontend (spec 04)
- Deployment automation (manual deploy is fine)
