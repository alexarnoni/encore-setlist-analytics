# Spec 01 — Implementation progress

Tracks the approved plan for `docs/specs/spec-01-ingestion.md`, including the
11 adjustments requested during review. Updated and committed at the end of
every task, marking items done and recording decisions made along the way
(versions pinned, table names, deviations from the original spec text).

## Adjustments approved before implementation started

1. Item 12: representative release uses the **mode** of track count among
   official releases (not the maximum), then earliest date, then country
   GB > US > XW.
2. Airflow: pin the latest stable **3.x** release; start from the official
   docker-compose for that version (`api-server`, `scheduler`,
   `dag-processor`, `triggerer` if needed); install via the official
   constraints file.
3. dbt: install in a separate virtualenv inside the Airflow image
   (`/opt/dbt-venv`) to avoid dependency conflicts with Airflow's own
   environment.
4. Item 5 (Airflow image): no `buildx` multi-platform build needed — just
   make sure the base image and packages support arm64; the VM builds
   natively.
5. Item 3 (schemas/tables): besides the init scripts (which only run on an
   empty volume), schema/table creation must be idempotent
   (`CREATE ... IF NOT EXISTS`) and runnable on demand via a task or command.
   Document this in the README.
6. DAG: add a `raw_setlistfm` truncate task at the **start** of the run, in
   addition to the final cleanup with `trigger_rule=all_done`.
7. `check_api_budget`: sum today's setlist.fm requests already logged in
   `ops.pipeline_runs`, estimate this run's cost from the last successful
   run (default 475 if there is none), and fail with a clear message if the
   total would exceed 1,300.
8. `extract_setlistfm` mapped task: use `max_active_tis_per_dag=1` to force
   sequential execution across bands.
9. Item 11: do **not** delete `src/clients.py`. Move it to
   `notebooks/phase0_clients.py` and update the notebook's import,
   keeping outputs cleared.
10. Integration tests: use a separate `postgres-test` service in
    `infra/docker-compose.yml` under a `test` profile, bound to
    `127.0.0.1:5436`. Document how to run it.
11. Add an optional `ENCORE_BANDS_FILTER` env var (list of band names) to
    limit extraction. The first real run (task 21) uses a single band.

## Checklist

- [x] **1. Representative release selection** — `select_representative_release`
      in `src/encore/ingestion/musicbrainz.py`, tie-break order: mode of
      track count → earliest date → country (GB > US > XW). Tests in
      `tests/test_representative_release.py` (7 cases, all passing).
      No deviation from the adjusted spec.
- [x] **2. Airflow infra baseline** — `infra/docker-compose.yml` created,
      merged with item 7 (same deliverable — see decisions log). Pinned
      Airflow **3.3.2** (latest stable as of 2026-09-17). Services:
      `postgres`, `airflow-init`, `airflow-api-server`, `airflow-scheduler`,
      `airflow-dag-processor`, plus `postgres-test` (adjustment 10 / item
      23, profile `test`, `127.0.0.1:5436`). No Redis/worker/Flower (LocalExecutor
      doesn't need Celery); triggerer omitted (no deferrable operators in
      spec-01). All ports bound to `127.0.0.1`, verified by grep. YAML
      syntax validated with `yaml.safe_load` (Docker not available in this
      environment — `docker compose config` still needs to be run where
      Docker is installed). `infra/postgres/init/01_create_encore_database.sh`
      creates the `encore` database alongside `airflow` (idempotent
      `WHERE NOT EXISTS`); full schema creation is still item 6.
- [x] **3. dbt in separate venv** — `airflow/Dockerfile` creates
      `/opt/dbt-venv` with `dbt-core==1.12.3` + `dbt-postgres==1.11.0`
      (latest stable pairing confirmed via web search on 2026-09-17,
      compatible with Postgres 16). Not added to `PATH`; called via
      `/opt/dbt-venv/bin/dbt` so it never shadows Airflow's own
      `python`/`pip`. Merged with item 8 (same Dockerfile) — see decisions
      log.
- [x] **4. `config/bands.yaml`** — already existed in the working tree
      (not created by Claude, found untracked before this task). Verified
      all 7 MBIDs against the Phase 0 MusicBrainz search cache
      (`data/raw/musicbrainz/search_artist_*.json`, gitignored, not in the
      repo): every band's top match has score 100 and its MBID matches the
      file exactly. Added `src/encore/config.py` (`load_bands()`) and
      `tests/test_config.py` (7 bands, UUID format, exact match against the
      Phase 0 values) as a regression guard.
- [x] **5. `.env.example`** — cross-checked against every `${VAR}`
      reference in `infra/docker-compose.yml`
      (`grep -oE '\$\{[A-Z_]+' infra/docker-compose.yml`): all covered
      except `AIRFLOW_PROJ_DIR` and `ENV_FILE_PATH` (documented as
      commented-out advanced overrides, since the compose file already
      defaults them for the normal case) and `HOSTNAME` (shell-provided
      inside the container, not a `.env` var). Includes `SETLISTFM_API_KEY`
      (matches the variable name already used in the local `.env` and in
      `src/clients.py`) and `ENCORE_BANDS_FILTER` (adjustment 11).
- [x] **6. Idempotent schema creation** — the 6 schemas from
      `structure.md` (`raw_setlistfm`, `raw_musicbrainz`, `staging`,
      `intermediate`, `analytics`, `ops`). Two paths, both idempotent
      (`CREATE SCHEMA IF NOT EXISTS`): `infra/postgres/init/02_create_schemas.sh`
      (first boot only, explicitly targets `--dbname encore` since init
      scripts otherwise connect to `$POSTGRES_DB`, i.e. the airflow
      metadata db) and `python -m encore.db` (on demand, any time) via
      `src/encore/db.py` (`get_connection()` + `ensure_schemas()`). Merged
      with item 10 (`src/encore/db.py`) — same file, see decisions log.
      Documented in a new minimal `README.md` ("Database schema
      bootstrap" section; full README content is still item 24). Unit
      tests in `tests/test_db.py` use a mocked connection (no Docker in
      this environment); a real integration run against `postgres-test`
      is still pending (item 23).
      **Table** creation (`raw_setlistfm.*`, `raw_musicbrainz.*`,
      `ops.pipeline_runs`) is separate and still pending — items 15–17.
- [x] **7. `infra/docker-compose.yml`** — done together with item 2 above.
- [x] **8. `airflow/Dockerfile`** — done together with item 3 above. Base
      `apache/airflow:3.3.2-python3.12` (official image, multi-arch —
      confirmed amd64+arm64 via web search, no buildx needed). Installs
      `airflow/requirements.txt` (requests, python-dotenv, psycopg2-binary,
      PyYAML — kept separate from the top-level `requirements.txt`, which
      also carries notebook/analysis/test tooling not needed in this
      image) constrained by the official Airflow 3.3.2/Python 3.12
      constraints file. Copies `src/` and `config/` into the image.
      `infra/docker-compose.yml` now builds this image via `build:` instead
      of pulling `apache/airflow` directly. Added `.dockerignore` at repo
      root (build context is now the repo root) to keep `.venv`, `.git`,
      `data/`, notebooks and caches out of the build.
- [ ] **9. Airflow log cleanup** — logs older than 14 days removed.
- [x] **10. `src/encore/db.py`** — done together with item 6 above.
- [ ] **11. `src/encore/clients/musicbrainz.py`** — moved from
      `src/clients.py`, keeps disk cache, rate limit, backoff, counters.
- [ ] **12. `src/encore/clients/setlistfm.py`** — moved from
      `src/clients.py`, disk cache removed, rate limit/backoff/counters kept.
- [ ] **13. Unit tests for clients** — mocked HTTP: pagination, 429 retry,
      request counters.
- [ ] **14. Preserve Phase 0 client** — move `src/clients.py` to
      `notebooks/phase0_clients.py`, update the notebook's import, keep
      outputs cleared.
- [ ] **15. MusicBrainz extraction (full)** — studio albums, representative
      release tracks, all recordings with `first-release-date`; upsert into
      `raw_musicbrainz`; skip if data younger than 30 days (configurable).
- [ ] **16. setlist.fm extraction (ephemeral)** — paginate to last page,
      load `raw_setlistfm.setlists` and `raw_setlistfm.setlist_entries`,
      optional raw JSON in the same schema, abort above the request budget.
- [ ] **17. `ops.pipeline_runs`** — schema and `log_run(...)` writer.
- [ ] **18. `airflow/dags/encore_pipeline.py`** — tasks in order:
      `truncate_raw_setlistfm_start`, `check_api_budget`,
      `extract_musicbrainz`, `extract_setlistfm` (mapped,
      `max_active_tis_per_dag=1`), `validate_raw`, `transform` (placeholder),
      `cleanup_raw_setlistfm` (`trigger_rule=all_done`), `log_run`;
      `schedule="@monthly"`, `max_active_runs=1`, `catchup=False`.
- [ ] **19. `check_api_budget` logic** — sum today's logged setlist.fm
      requests + estimate from last successful run (default 475), fail
      clearly above 1,300.
- [ ] **20. `validate_raw`** — row counts per band, % setlists with ≥1 song,
      fails if any band returns zero setlists.
- [ ] **21. `cleanup_raw_setlistfm` (final)** — truncates every table in
      `raw_setlistfm`, `trigger_rule=all_done`.
- [ ] **22. Analytics schema guard test** — fails if any table in
      `analytics` has a column named `setlist_id`.
- [ ] **23. Integration test setup** — `postgres-test` service added to
      `infra/docker-compose.yml` (done, in item 2). Still pending: actual
      integration tests that use it, and documented run instructions in
      README (item 24).
- [ ] **24. `README.md`** — summary, Mermaid architecture diagram, data
      policy, local run instructions (including idempotent schema
      creation and `ENCORE_BANDS_FILTER`), VM deploy steps, setlist.fm
      attribution.
- [ ] **25. First real run** — single band via `ENCORE_BANDS_FILTER`,
      verify all acceptance criteria (raw_setlistfm empty at the end,
      raw_musicbrainz populated without duplicates, no port on 0.0.0.0,
      `ops.pipeline_runs` request counts, full test suite passing).

## Decisions log

- **2026-09-17** — Testing framework: **pytest 8.3.4**, pinned in
  `requirements.txt`; `pytest.ini` sets `pythonpath = src` and
  `testpaths = tests` so `import encore...` works without installing the
  package.
- **2026-09-17** — Repo hygiene fix (pre-task-1): `CLAUDE.md`, `product.md`,
  `tech.md`, `structure.md`, `spec-01-ingestion.md` were at the repo root;
  moved to `docs/context/` and `docs/specs/` per `structure.md`, no content
  change.
- **2026-09-17** — Airflow version pinned to **3.3.2** (confirmed latest
  stable via web search on this date). Constraints file for the Dockerfile
  (item 8) will be
  `https://raw.githubusercontent.com/apache/airflow/constraints-3.3.2/constraints-3.12.txt`.
- **2026-09-17** — Checklist items 2 and 7 were the same deliverable
  (`infra/docker-compose.yml`); implemented together under item 2 and both
  marked done to avoid duplicate work in a later task.
- **2026-09-17** — Executor: **LocalExecutor** confirmed per `tech.md`, so
  the compose file drops Redis, `airflow-worker` and `flower` from the
  official baseline. Auth manager kept as `FabAuthManager` (official
  default); `AIRFLOW__CORE__LOAD_EXAMPLES` set to `'false'` (deviation from
  the official example's `'true'`, since example DAGs have no place in
  this project).
- **2026-09-17** — Triggerer service omitted from `infra/docker-compose.yml`.
  Spec-01 has no deferrable operators; revisit if a later spec needs one.
- **2026-09-17** — Single PostgreSQL instance holds both the `airflow` and
  `encore` databases (per `tech.md`), created via
  `infra/postgres/init/01_create_encore_database.sh` (`airflow` comes from
  `POSTGRES_DB`, `encore` is created idempotently by the script). Schemas
  inside `encore` are still pending (item 6).
- **2026-09-17** — Could not run `docker compose config` or `docker compose
  up` in this environment (Docker CLI not installed). Validated the compose
  file with `python -c "import yaml; yaml.safe_load(...)"` instead and
  manually confirmed every `ports:` entry is bound to `127.0.0.1`. Full
  `docker compose up` verification is still needed on a machine with Docker
  before item 25 (first real run).
- **2026-09-17** — dbt versions pinned: `dbt-core==1.12.3`,
  `dbt-postgres==1.11.0` (latest stable pairing per web search on this
  date, supports Postgres 16/17/18). Not re-verified by an actual build —
  `docker build` for `airflow/Dockerfile` still needs to run on a machine
  with Docker to confirm these versions resolve and install cleanly.
- **2026-09-17** — Checklist items 3 and 8 were the same deliverable
  (`airflow/Dockerfile`); implemented together and both marked done.
- **2026-09-17** — `infra/docker-compose.yml` changed from pulling
  `apache/airflow:3.3.2` directly to building `../airflow/Dockerfile`
  (`build:` + `image:` on `x-airflow-common`), since the custom image
  (project code + dbt venv) is required by `tech.md`, not optional.
- **2026-09-17** — Added `.dockerignore` at the repo root: the Docker build
  context became the repo root once `airflow/Dockerfile` needed to `COPY
  src/` and `config/` (paths outside `airflow/`). Excludes `.venv`, `.git`,
  `data/`, `notebooks/`, `.env`, caches and markdown files from the build
  context.
- **2026-09-17** — Added `PyYAML==6.0.2` to the top-level `requirements.txt`
  (already an indirect dependency via `jupyter`, but `src/encore/config.py`
  now imports it directly so it needs its own pin).
- **2026-09-17** — Checklist items 6 and 10 were the same deliverable
  (`src/encore/db.py`); implemented together and both marked done.
- **2026-09-17** — `encore.db.get_connection()` always targets the
  `encore` database by a hardcoded `DATABASE_NAME` constant, independent
  of `POSTGRES_DB` (which names Airflow's own metadata database). Reads
  `POSTGRES_HOST`/`POSTGRES_PORT` from the environment with defaults
  (`postgres`/`5432`) matching the Docker network; outside the
  `airflow-*` containers (e.g. running `python -m encore.db` from a host
  shell) these must be overridden to `localhost`/`5435`.
- **2026-09-17** — Created a minimal `README.md` ahead of item 24, to
  satisfy adjustment 5's requirement that the on-demand schema bootstrap
  command be documented there. Item 24 will expand it (architecture
  diagram, deploy steps, attribution, etc.) without redoing this section.
- **2026-09-17** — Fix (user-flagged): `infra/docker-compose.yml` fell back
  to a hardcoded `airflow` default whenever `POSTGRES_PASSWORD`,
  `AIRFLOW_FERNET_KEY`, `AIRFLOW_JWT_SECRET` or `AIRFLOW_WWW_USER_PASSWORD`
  were unset — a real (if weak) password committed in a public repo.
  Replaced every password/secret fallback with Compose's `${VAR:?message}`
  syntax so `docker compose up` refuses to start instead of silently using
  a guessable credential. Non-secret vars (`POSTGRES_USER`, `POSTGRES_DB`,
  `AIRFLOW_WWW_USER_USERNAME`) keep their plain defaults. Updated
  `.env.example` to mark these four as required with no default.
