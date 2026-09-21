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
      bootstrap" section; full README content is still item 24).
      **Verified for real on 2026-09-17** once Docker became available
      (see "Docker validation pass" below): `docker compose up -d
      postgres` ran both init scripts, `\dn` inside the container showed
      all 6 schemas, and `python -m encore.db` run a second time against
      the already-initialized database completed with no errors
      (idempotency confirmed against a real Postgres, not just mocks).
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
      **Verified for real on 2026-09-17**: `docker compose build`
      succeeds (with a fix, see decisions log), `dbt --version` inside
      `/opt/dbt-venv` reports `dbt-core 1.12.3` / `postgres 1.11.0`, `dbt`
      is confirmed absent from `PATH`, and `python -c "import
      encore..."` works inside the image.

### Docker validation pass (2026-09-17)

The user installed Docker Desktop mid-session. Ran the full local stack
for the first time against real Docker/PostgreSQL/Airflow and fixed
three real bugs this surfaced (all itemized in the decisions log below):
`docker compose up` failing outside `infra/` without `--env-file`, a
pip dependency conflict between `airflow/requirements.txt`'s pinned
`requests==2.32.3` and Airflow's own constraints file, and `airflow
db migrate` failing as root (`user: "0:0"`) inside `airflow-init`.
After the fixes: `docker compose up -d postgres` → healthy, both init
scripts ran; `docker compose build` → succeeded; `airflow-init` →
migration completed, admin user created; `airflow-scheduler`,
`airflow-dag-processor`, `airflow-api-server` → all reached `healthy`;
`GET /api/v2/monitor/health` → all green (scheduler, dag_processor,
metadatabase; triggerer `null` as expected, none configured);
`airflow dags list-import-errors` → none (only `.gitkeep` in
`airflow/dags/` so far). Stack torn down with `docker compose down`
afterward.
- [x] **9. Airflow log cleanup** — logic in `src/encore/log_cleanup.py`
      (`delete_old_logs()`, pure filesystem function, no Airflow import
      — covered by the fast unit suite, 6 tests: missing dir, age
      threshold with a just-under-boundary case, default 14-day
      constant, and empty-directory cleanup after deletion). Wrapped in
      a separate daily DAG, `airflow/dags/log_cleanup.py`
      (`schedule="@daily"`), rather than a task inside
      `encore_pipeline` — log retention runs on its own cadence,
      independent of the monthly ingestion schedule. Verified via a
      live `DagBag` load in the built image: zero import errors,
      correct daily cron schedule, one task
      (`clean_airflow_logs`).
- [x] **10. `src/encore/db.py`** — done together with item 6 above.
- [x] **11. `src/encore/clients/musicbrainz.py`** — logic moved from
      `src/clients.py`, keeps disk cache (R3.3), rate limit, backoff,
      counters. Retry/backoff/counter logic factored out into a new
      shared `src/encore/clients/_http.py` (`request_with_retry`,
      `get_counters`, `reset_counters`) so `setlistfm.py` (item 12) reuses
      it instead of duplicating ~50 lines — not explicitly required by
      R3.1 but a direct consequence of moving both clients out of the
      single `src/clients.py` file into separate modules. `get_cache_hits`
      (Phase-0-only debugging counter) was **not** carried over — not a
      spec-01 requirement.
- [x] **12. `src/encore/clients/setlistfm.py`** — logic moved from
      `src/clients.py`, disk cache **removed** entirely (R3.2 — every call
      hits the network; caching would defeat the ephemeral-data policy).
      Reuses `_http.request_with_retry` from item 11 instead of
      duplicating retry/counter logic.
- [x] **13. Unit tests for clients** — mocked HTTP (`unittest.mock`, no
      `responses`/`requests-mock` dependency added). MusicBrainz: real
      request writes cache + increments counter, cache hit skips both,
      429-then-success retry, pagination params. setlist.fm: missing API
      key raises, session carries the `x-api-key` header, two identical
      calls both hit the network and nothing is written to the temp cwd
      (proves no disk cache), pagination param, 503-then-success retry,
      exhausting all 3 retries raises `RuntimeError`. `time.sleep` mocked
      throughout so the suite stays fast (22 tests, 0.34s). Still **not**
      covered here: a live round trip against a real setlist.fm response
      or a real `raw_setlistfm` table — blocked on Docker (see decisions
      log); that gap is what items 18/23/25 close later.
- [x] **14. Preserve Phase 0 client** — `src/clients.py` moved
      (`git mv`, history preserved) to `notebooks/phase0_clients.py`,
      docstring updated to mark it frozen/Phase-0-only. Notebook's import
      cell updated (`sys.path` now points at the notebook's own directory,
      `from phase0_clients import ...`), outputs re-cleared with
      `jupyter nbconvert --clear-output --inplace` and verified empty.
      Sanity-checked that `CACHE_DIR`/`.env` path resolution still points
      at the repo root from the new location.
- [x] **15. MusicBrainz extraction (full)** — added to
      `src/encore/ingestion/musicbrainz.py` (alongside
      `select_representative_release`): `ensure_tables()` creates
      `raw_musicbrainz.albums` (PK `release_group_mbid`),
      `.album_tracks` (PK `release_group_mbid, recording_mbid`, FK to
      `.albums`) and `.recordings` (PK `recording_mbid`) — table design
      not specified by R5, chosen to satisfy "no duplicates across runs"
      (R5.5) via `ON CONFLICT ... DO UPDATE`. `fetch_studio_albums`
      filters `primary-type == "Album"` with no `secondary-types` (R5.1),
      paginated. `fetch_all_recordings` paginates with the R5.2 500-page
      guard. `extract_band()` ties it together: skip via
      `should_skip_band()` if data is younger than `refresh_after_days`
      (default 30, R5.6), else upsert albums → representative release's
      tracks → all recordings, one `conn.commit()` per band. 10 unit
      tests with mocked client + mocked DB connection (pagination
      filtering, skip logic fresh/stale/no-data, upsert SQL shape, empty
      release-group edge case).
      **Verified against a real PostgreSQL on 2026-09-17** (ad hoc script,
      not a committed test — see decisions log): `ensure_tables()` runs
      clean, `extract_band()` called twice with identical mocked API data
      leaves exactly 1 album / 2 tracks / 1 recording (no duplicates,
      R5.5 confirmed for real), and calling it a third time with the
      default 30-day threshold correctly skips without touching the
      client (R5.6 confirmed for real).
- [x] **16. setlist.fm extraction (ephemeral)** — added
      `src/encore/ingestion/setlistfm.py`. `ensure_tables()` creates
      `raw_setlistfm.setlists` (PK `setlist_id`), `.setlist_entries` (PK
      `setlist_id, set_idx, position`, FK to `.setlists`) and
      `.raw_responses` (PK `setlist_id`, JSONB payload) — table design
      not specified by R4, mirrors item 15's approach. `fetch_all_setlists`
      paginates `/artist/{mbid}/setlists` to the last page (R4.1) and
      raises `RuntimeError` if the real-request counter would exceed
      `MAX_REQUESTS_PER_RUN = 1300` (R4.4) — a hard per-run safety net,
      separate from the smarter cross-run budget estimate that item 19's
      `check_api_budget` task will implement. `parse_setlist()` splits one
      setlist.fm response object into a `setlists` row and its
      `setlist_entries` rows: a "set" block is `is_encore=True` when the
      API marks it with an `encore` field; a song is `is_cover` when it
      has a `cover` object (with `cover_artist` from `cover.name`); `tape`
      maps to `is_tape`. Raw JSON is stored only when
      `ENCORE_STORE_RAW_SETLISTFM_JSON` is truthy (R4.3 — "only if needed
      for debugging"), off by default. `extract_band()` ties it together,
      one `conn.commit()` per band. 6 unit tests with mocked client + DB.
      **Verified against a real PostgreSQL on 2026-09-17**: `ensure_tables()`
      runs clean, `extract_band()` called twice with identical mocked data
      leaves exactly 1 setlist / 2 entries (no duplicates), `run_id`
      correctly updates to the latest run, and `TRUNCATE
      raw_setlistfm.setlist_entries, raw_setlistfm.setlists,
      raw_setlistfm.raw_responses` (the same statement `cleanup_raw_setlistfm`,
      item 21, will run) empties every table — the first real proof that
      the ephemeral-data mechanism actually works end to end, ahead of
      items 18/21 building the DAG task around it.
- [x] **17. `ops.pipeline_runs`** — added `src/encore/ops.py`:
      `ensure_tables()` creates the table (PK `run_id`, `started_at`,
      `finished_at`, `status`, `setlistfm_requests`,
      `musicbrainz_requests`, `setlists_per_band` JSONB,
      `error_message`), `log_run(...)` upserts one row per run (`ON
      CONFLICT (run_id) DO UPDATE`) so a retried/re-logged run doesn't
      duplicate. One row is written once at the end by the DAG's
      `log_run` task (R6.7), not incrementally per task. 3 unit tests
      with a mocked connection. **Verified against a real PostgreSQL on
      2026-09-17**: logging the same `run_id` twice with different data
      leaves exactly one row with the second call's values.
- [x] **18. `airflow/dags/encore_pipeline.py`** — done together with
      items 19, 20 and 21 below (same file, built as one working DAG
      rather than four disconnected fragments — see decisions log).
      TaskFlow API, `from airflow.sdk import dag, task` (the
      non-deprecated Airflow 3 import; `airflow.decorators` still works
      but warns). Task order verified via a live `airflow.models.DagBag`
      load inside the built image (not just eyeballing the code):
      `truncate_raw_setlistfm_start → check_api_budget →
      extract_musicbrainz → extract_setlistfm → validate_raw → transform
      → cleanup_raw_setlistfm → log_run`. Confirmed on the loaded DAG
      object: `max_active_runs=1`, `catchup=False`, schedule
      `0 0 1 * *` UTC (monthly), `extract_setlistfm.max_active_tis_per_dag
      == 1` (adjustment 8), `cleanup_raw_setlistfm`/`log_run`
      `trigger_rule=TriggerRule.ALL_DONE` with the right upstream sets so
      both still run when an earlier task fails. `import_errors == {}`.
      **Not yet triggered as a real DAG run** (needs real API keys/DB
      and would spend real setlist.fm quota) — that's item 25.
      **Known simplification**: `log_run`'s success/failure status uses
      a heuristic (every upstream argument it receives is non-None) since
      Airflow doesn't push an XCom for a task that raised; documented as
      a judgment call in the decisions log, not verified against an
      actual induced failure.
- [x] **19. `check_api_budget` logic** — `ops.sum_setlistfm_requests_today()`
      + `ops.estimate_next_run_setlistfm_cost()` (default 475, tech.md's
      full 7-band load) added to `src/encore/ops.py`; the DAG task raises
      `AirflowFailException` with the exact projected/logged/estimated
      numbers if their sum exceeds 1,300. 4 unit tests with a mocked
      connection.
- [x] **20. `validate_raw`** — `sf_ingestion.validate_bands()` added to
      `src/encore/ingestion/setlistfm.py`: per-band row counts and % of
      setlists with ≥1 song; raises `ValueError` (turned into
      `AirflowFailException` by the DAG task) if any band has zero
      setlists. Relies on `raw_setlistfm` having been truncated at the
      *start* of the run (item 18's `truncate_raw_setlistfm_start`), so
      no `run_id` filter is needed — whatever's in the table belongs to
      this run only. 2 unit tests with a mocked connection.
- [x] **21. `cleanup_raw_setlistfm` (final)** — `sf_ingestion.truncate_all()`
      added to `src/encore/ingestion/setlistfm.py`, shared by both the
      start-of-run truncate (item 18) and this final cleanup
      (`trigger_rule=all_done`) — one function, two call sites, so the
      truncate logic can't drift between them. 1 unit test with a mocked
      connection.
- [x] **22. Analytics schema guard test** — done together with item 23
      (`tests/integration/test_analytics_schema_guard.py`, same
      infrastructure). Queries `information_schema.columns` for
      `table_schema = 'analytics' AND column_name = 'setlist_id'`.
      Passes vacuously today (no tables in `analytics` yet — marts land
      in spec 02); a second test plants a throwaway violating table and
      confirms the guard actually detects it (then cleans up), so the
      passing-today result isn't just "nothing to check yet" masquerading
      as coverage.
- [x] **23. Integration test setup** — `postgres-test` service was
      already in `infra/docker-compose.yml` (item 2). Added
      `tests/integration/` (excluded from the default `pytest` run via
      `norecursedirs = integration` in `pytest.ini`, so the fast suite
      never needs Docker): `conftest.py`'s `pg_connection` fixture
      connects to `postgres-test` and calls `pytest.skip(...)` if it
      isn't reachable (session-scoped, so a full skip run costs ~5s, not
      ~50s — the first version reconnected per test). 12 tests total,
      promoting this session's earlier ad hoc `python -c` integration
      checks (items 6, 15, 16, 17) into committed, repeatable tests, plus
      the item 22 schema guard. All 12 pass against a real
      `postgres-test`; all 12 skip cleanly when it isn't running.
      Documented in `README.md`'s new "Integration tests" section.
- [x] **24. `README.md`** — expanded the minimal version from items 6/9
      into the full R9 document: project summary, a Mermaid architecture
      diagram (solid = built in spec-01, dashed = later specs — encore
      pipeline DAG, dbt/marts/API/frontend), a "Data policy" section
      condensed from `product.md` (ephemeral setlist.fm data, no
      per-show pages, the `setlist_id`-in-`analytics` guard, mandatory
      attribution — flagged as not yet implemented since there's no
      frontend until spec 04), local run instructions (now mentioning
      `ENCORE_BANDS_FILTER` and the Airflow UI), the existing schema
      bootstrap and integration test sections, and a new "Deploying to
      the VM" section (manual, per `tech.md`'s Oracle VM/port/SSH-tunnel
      details — spec-01 explicitly leaves deploy automation for later).
      Diagram syntax verified for real: rendered it with
      `npx @mermaid-js/mermaid-cli` to a 27KB SVG with no errors, not
      just eyeballed.
- [x] **25. First real run** — `ENCORE_BANDS_FILTER=Oasis` (958 shows,
      the smallest band in the Phase 0 table, to spend the least real
      setlist.fm quota). Rebuilt the image, brought up the full stack,
      unpaused `encore_pipeline`. Unpausing itself triggered a
      `scheduled__2026-09-01` run (the most recent monthly boundary,
      expected with `catchup=False`) in addition to a `manual` trigger —
      `max_active_runs=1` queued the second behind the first, giving two
      real, real-API runs back to back instead of one.

      **Run 1** (`scheduled__2026-09-01`): all 8 tasks succeeded.
      `extract_musicbrainz` → Oasis: 9 albums, 78 tracks, 5,596
      recordings, 66 MusicBrainz requests. `extract_setlistfm` → 958
      setlists, 13,170 entries, 48 setlist.fm requests. `validate_raw` →
      "Oasis: 891/958 setlists with songs (93.0%)" — **958 shows / 93.0%
      matches the Phase 0 validated table exactly**
      (`.kiro/specs/encore-fase0-validacao/requirements.md`), a strong
      real-world cross-check that the production pipeline reproduces
      Phase 0's numbers.

      **Run 2** (`manual`, ran immediately after): also succeeded.
      MusicBrainz requests = 0 (the 30-day skip logic correctly skipped
      re-fetching Oasis's fresh data) and `raw_musicbrainz` row counts
      were unchanged after the second run (9/78/5,596) — no duplicates,
      confirmed via the real Airflow DAG, not just the ad hoc/mocked
      checks from earlier items.

      **All acceptance criteria checked directly against the running
      containers and the database, not inferred:**
      - `raw_setlistfm.setlists`/`.setlist_entries`: 0 rows after both
        runs (`cleanup_raw_setlistfm` confirmed working end to end).
      - `raw_musicbrainz`: 9/78/5,596 after both runs, unchanged.
      - `ops.pipeline_runs`: 2 rows, both `status='success'`,
        `setlistfm_requests` 48 and 48 (96 total today — well under the
        1,300 budget check's threshold), `musicbrainz_requests` 66 then
        0.
      - `docker compose ps --format "table {{.Names}}\t{{.Ports}}"` on
        the live containers: every published port is `127.0.0.1:*`,
        nothing on `0.0.0.0` (`airflow-scheduler`/`airflow-dag-processor`
        don't even publish 8080 to the host at all, only
        `airflow-api-server` and `postgres` do).
      - Full test suite: 55 unit + 12 integration (with `postgres-test`
        up) = 67 passing.

      **Found and fixed during this run**: `raw_musicbrainz` had 1 extra
      album/track/recording beyond Oasis's — leftover fake test data
      (`band_name='Muse'`, ids `rg1`/`rec1`) from this session's earlier
      ad hoc integration checks for items 15/16 (run against this same
      main Postgres, not `postgres-test`). Not a pipeline bug — deleted
      the 3 leftover rows by hand and re-verified the counts matched
      `extract_musicbrainz`'s own reported numbers exactly (9/78/5,596)
      afterward. Lesson for next time: ad hoc verification scripts
      against the main `encore` database (as opposed to `postgres-test`)
      should clean up after themselves, or use `postgres-test` even for
      one-off checks.

      Reset `ENCORE_BANDS_FILTER` back to empty in the local `.env`
      afterward (it was only for this run) and tore the stack down with
      `docker compose down` (not `-v`, so the volume — including this
      real Oasis/ops data — persists).

      **This closes spec-01.** All 25 checklist items are done.

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
- **2026-09-17** — Confirmed Docker is **not installed** in this dev
  environment (no `docker` on PATH, no Docker Desktop under
  `C:\Program Files`) — the user reformatted their machine and hasn't
  reinstalled it yet. This blocks any integration test that needs a real
  PostgreSQL: items 13 (setlist.fm client's disk-cache-removed behavior
  is easy to unit-test, but a live setlist.fm/raw_setlistfm round trip
  is not), 14/18 (proving the ephemeral-data policy — `raw_setlistfm`
  actually empties at run end — needs a real DB), and 23
  (`postgres-test` integration suite). Those pieces will be implemented
  as code + unit tests now and flagged for a follow-up integration run
  once Docker is available; item 25 (first real run) cannot happen at
  all until then.
- **2026-09-17** — Item 11 note: chose to factor retry/backoff/counter
  logic into `src/encore/clients/_http.py` rather than duplicating it in
  both `musicbrainz.py` and the upcoming `setlistfm.py`. Not asked for
  explicitly, but keeping ~50 lines of retry logic in one place instead
  of two seemed like the obviously correct call while splitting
  `src/clients.py` apart — flagging it here in case it should be
  reconsidered.
- **2026-09-17** — Fix (user-flagged): `infra/docker-compose.yml` fell back
  to a hardcoded `airflow` default whenever `POSTGRES_PASSWORD`,
  `AIRFLOW_FERNET_KEY`, `AIRFLOW_JWT_SECRET` or `AIRFLOW_WWW_USER_PASSWORD`
  were unset — a real (if weak) password committed in a public repo.
  Replaced every password/secret fallback with Compose's `${VAR:?message}`
  syntax so `docker compose up` refuses to start instead of silently using
  a guessable credential. Non-secret vars (`POSTGRES_USER`, `POSTGRES_DB`,
  `AIRFLOW_WWW_USER_USERNAME`) keep their plain defaults. Updated
  `.env.example` to mark these four as required with no default.
- **2026-09-17** — Docker Desktop installed mid-session (previously
  unavailable). Installed to a non-standard path
  (`AppData\Local\Programs\DockerDesktop`, not `Program Files`), so its
  `resources/bin` had to be added to `PATH` manually for this session —
  future sessions on this machine may need the same until the user's
  normal shell profile picks up the installer's PATH change.
- **2026-09-17** — Fix: `docker compose up` (or any `docker compose`
  command) run from `infra/` — or even from the repo root with `-f
  infra/docker-compose.yml` alone — fails every `${VAR:?...}` check with
  "variable is missing a value", even though `.env` exists at the repo
  root and is correctly filled in. Cause: Compose resolves its own
  `${VAR}` interpolation (as opposed to the `environment:`/`env_file:`
  values injected into containers) against a `.env` file in the *compose
  project directory* — the directory of the first `-f` file — not the
  directory the command is run from and not the repo root. Fix: always
  invoke Compose with an explicit `--env-file .env` from the repo root:
  `docker compose -f infra/docker-compose.yml --env-file .env <cmd>`.
  Documented in `infra/docker-compose.yml`'s header comment and in
  `README.md`'s new "Running locally" section.
- **2026-09-17** — Fix: `docker compose build` failed with
  `ResolutionImpossible` — `airflow/requirements.txt` pinned
  `requests==2.32.3`, which conflicts with Airflow 3.3.2's own official
  constraints file (`constraints-3.12.txt`), which pins
  `requests==2.34.2`. Fix: dropped all version pins from
  `airflow/requirements.txt` (`requests`, `python-dotenv`,
  `psycopg2-binary`, `PyYAML` with no `==`), since the file is installed
  with `--constraint <official constraints file>` anyway — the
  constraints file already fixes exact versions for anything it manages,
  and pinning the same package again here can only conflict with it, not
  usefully override it. General lesson for item 8/anything installed
  under an Airflow constraints file going forward: don't pin versions in
  `airflow/requirements.txt`.
- **2026-09-17** — Fix: `airflow-init`'s `airflow db migrate` /
  `airflow users create` failed with `ModuleNotFoundError: No module
  named 'airflow'` — but only when run as root (`user: "0:0"`, needed so
  the container can `chown` the mounted logs volume); the exact same
  commands work fine as the `airflow` user (uid 50000). Root cause:
  `/home/airflow/.local` is a real Python venv (it has its own
  `pyvenv.cfg`) where Airflow itself is installed, but the `airflow`
  console-script's shebang points straight at the base interpreter
  (`/usr/python/bin/python3.12`), bypassing PEP 405 venv detection
  entirely. That base interpreter only picks up the venv's
  site-packages as a fallback via Python's ordinary user-site-packages
  mechanism, which resolves through `$HOME` — `/home/airflow/.local`
  for the `airflow` user (matches), `/root` for root (doesn't). Fix:
  in `airflow-init`'s command script, run `su airflow -c "airflow
  ..."` for both the migrate and user-create steps instead of invoking
  `airflow` directly as root (root is still needed, and kept, for the
  preceding `mkdir`/`chown` on the logs volume). This is specific to
  this Airflow image's package layout, not a general Docker/Compose
  issue — worth re-checking if a future Airflow base image version
  changes how it installs itself.
- **2026-09-17** — Full Docker validation pass completed successfully
  after the three fixes above: `postgres`, `airflow-init`,
  `airflow-scheduler`, `airflow-dag-processor`, `airflow-api-server` all
  came up healthy; schema bootstrap (item 6) and the Airflow+dbt image
  (items 3/8) are now confirmed against real infrastructure, not just
  unit tests/mocks. Items 13 (setlist.fm live round trip), 14/18 (the
  ephemeral-data policy — `raw_setlistfm` actually emptying), and 23
  (the `postgres-test` integration suite) still need their own
  integration runs once the corresponding ingestion/DAG code exists —
  today's pass only validated the infrastructure layer, not the pipeline
  logic on top of it.
- **2026-09-17** — Ran ad hoc integration checks for items 15 and 16
  against a real `docker compose up -d postgres` (mocked API client,
  real DB): both ingestion modules' upserts don't duplicate on a second
  run, MusicBrainz's 30-day skip logic works, and the exact `TRUNCATE`
  statement `cleanup_raw_setlistfm` (item 21) will run does empty
  `raw_setlistfm`. These were throwaway scripts run via `python -c`, not
  committed as tests — a proper `tests/integration/` suite using the
  `postgres-test` compose service (item 23) still needs to be written
  before spec-01 can be considered fully tested per R8; today's checks
  only reduce the risk that items 15/16's SQL is wrong, they don't
  replace item 23.
- **2026-09-18** — Checklist items 18-21 were the same file
  (`airflow/dags/encore_pipeline.py`); implemented and validated
  together rather than as four separate, temporarily-broken fragments.
- **2026-09-18** — Airflow 3 DAG-authoring import: confirmed via
  `docker run` that `from airflow.sdk import dag, task,
  get_current_context, TriggerRule` is the current, non-deprecated
  surface for Airflow 3.3.2 (`from airflow.decorators import dag, task`
  and `from airflow.exceptions import AirflowFailException` still work
  but print `DeprecatedImportWarning`, pointing at `airflow.sdk` and
  `airflow.sdk.exceptions` respectively). Used the non-deprecated forms.
- **2026-09-18** — Fix: `encore.config.load_bands()` (item 4) computed
  `config/bands.yaml`'s path as `Path(__file__).parents[2] / "config" /
  "bands.yaml"`, which assumes `config/` sits next to `src/` — true
  locally and in the notebook, but not inside the Airflow image, where
  `config/` is copied to `/opt/airflow/config-data/` specifically to
  avoid colliding with Airflow's own `/opt/airflow/config` directory.
  Loading the DAG inside the built image failed with `FileNotFoundError:
  /opt/airflow/config/bands.yaml` the first time it was tried. Fixed by
  adding an `ENCORE_BANDS_FILE` env var override to `load_bands()`,
  set to `/opt/airflow/config-data/bands.yaml` in `airflow/Dockerfile`.
  Added a unit test for the override. This is exactly the kind of bug
  that only surfaces by actually loading code inside the target
  environment — found by testing the DAG in Docker, not by reasoning
  about the code.
- **2026-09-18** — `log_run`'s success/failure determination is a
  judgment call, not specified by R6/R7: since a failed task never
  pushes an XCom, a downstream `trigger_rule=all_done` task like
  `log_run` sees `None`/missing values for anything upstream that
  failed. `transform()` was changed to return `True` (not bare `None`)
  specifically so a raised exception there is distinguishable from a
  normal successful run in `log_run`'s heuristic
  (`transformed is True`). This wasn't verified against an actual
  induced failure (would need a real DAG run — item 25, or a dedicated
  Airflow-level test using a live scheduler, which is out of scope for
  a unit test). Flagging in case a future spec needs stronger
  guarantees here (e.g. reading task instance states from the DAG run
  directly instead of relying on XCom presence).
- **2026-09-18** — Validated the built DAG structurally with a live
  `airflow.models.DagBag(dag_folder=...)` load inside the
  `encore-airflow:3.3.2` image (mounting `airflow/dags/` read-only) —
  confirmed zero import errors, exact task order, dependency edges,
  trigger rules, `max_active_tis_per_dag`, schedule, `max_active_runs`
  and `catchup`. This is stronger than a mocked unit test would be for
  DAG *structure*, but it is not a substitute for actually triggering a
  run (item 25) or for `tests/` coverage — `apache-airflow` was
  deliberately not added to the top-level `requirements.txt` (it's a
  very heavy dependency tree for a notebook/analysis dev venv), so the
  DAG file itself has no coverage in the fast local `pytest` suite;
  only the plain Python functions it calls into
  (`encore.ingestion.*`, `encore.ops`, `encore.clients.*`) do.
