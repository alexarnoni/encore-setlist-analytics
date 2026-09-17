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
- [ ] **2. Airflow infra baseline** — pin Airflow 3.x latest stable, adapt
      official docker-compose (`api-server`, `scheduler`, `dag-processor`,
      `triggerer` if needed), install via official constraints file.
- [ ] **3. dbt in separate venv** — `/opt/dbt-venv` inside the Airflow image.
- [ ] **4. `config/bands.yaml`** — 7 bands with name + MBID from Phase 0.
- [ ] **5. `.env.example`** — including `ENCORE_BANDS_FILTER`.
- [ ] **6. Idempotent schema/table creation** — init scripts for first boot
      plus an on-demand task/command using `CREATE ... IF NOT EXISTS`;
      documented in README.
- [ ] **7. `infra/docker-compose.yml`** — postgres, airflow services, ports
      bound to 127.0.0.1, named volumes, plus `postgres-test` under a
      `test` profile on `127.0.0.1:5436`.
- [ ] **8. `airflow/Dockerfile`** — official Airflow 3.x base, project
      requirements, dbt in its own venv; arm64-compatible, native build
      (no buildx).
- [ ] **9. Airflow log cleanup** — logs older than 14 days removed.
- [ ] **10. `src/encore/db.py`** — connection helpers from env vars.
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
- [ ] **23. Integration test setup** — `postgres-test` service, documented
      run instructions.
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
