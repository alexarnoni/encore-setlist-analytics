# Spec 02a — Implementation progress

Tracks the approved plan for `docs/specs/spec-02a-first-kpi.md`. Updated
and committed at the end of every task, marking items done and recording
decisions made along the way (versions pinned, schema choices,
deviations from the spec text) — same discipline as
`docs/specs/spec-01-progress.md`.

## Adjustments approved before implementation started

1. Item 1: the dev load must record its load timestamp in `ops` (or a
   simple table) and the README must state this data is temporary and
   must not be left in the database between work sessions. Item 22 must
   still end with `raw_setlistfm` empty.
2. Item 2: `dbt/profiles.yml` must contain only `env_var()` references,
   never literal credentials — verified no secret ends up in the repo.
3. Item 3: create the `unaccent` extension in `infra/postgres/init/`
   instead of a dbt `on-run-start` hook (`CREATE EXTENSION` needs
   superuser, which the app's runtime role won't have). The dbt hook
   may only check the extension exists and fail with a clear message if
   it doesn't.
4. Item 6: dbt unit tests apply to models, not macros directly. Cover
   `normalize_title` with a small test model applying the macro to
   fixed input values, plus a singular test comparing expected outputs.
5. Item 22: if `match_rate_by_performance` for Oasis is below 0.90,
   list the unmatched titles ordered by performance count and **stop
   for review** — do not fill `seed_song_overrides.csv` unilaterally.

## Open questions raised before implementation started

Flagged when the plan was proposed; resolved one way or another before
or during the corresponding task, with the actual resolution recorded
in the decisions log below.

1. **Medley split positions** (R2.2): the spec doesn't say how multiple
   rows born from splitting one `" / "`-joined entry share/subdivide
   `position`. Proposed default: each part keeps the original
   `position` and gets a new `medley_part` (1, 2, 3...) to disambiguate
   within the group.
2. **`dbt seed` "only when changed or on first run"** (R8.1): real
   change detection (hashing the seed CSVs) is more machinery than two
   small seed files justify. Proposed default: run `dbt seed` on every
   `transform` task — idempotent, negligible cost.
3. **Seed schema**: the spec doesn't say which schema seeds load into.
   Proposed default: `staging`, alongside the models that consume them.
4. **Local dbt development against ephemeral raw data**: `raw_setlistfm`
   is truncated at the end of every pipeline run, so staging models
   can't be iterated against real data without either running the full
   DAG repeatedly (spending real API quota each time) or loading data
   once and leaving it in place. Resolved by task 1 below: a one-off
   direct load (bypassing the DAG's cleanup) used for all subsequent
   local dbt work.

## Checklist

- [x] **1. Dev fixture: load real Oasis raw data without truncating** —
      `scripts/load_dev_fixture.py` calls
      `encore.ingestion.setlistfm.extract_band` +
      `encore.ingestion.musicbrainz.extract_band` directly against
      local Postgres, bypassing the DAG (and its cleanup). MusicBrainz
      extraction uses the default 30-day freshness check (not forced),
      so it naturally skips re-fetching Oasis's discography — already
      loaded by spec-01 item 25 — instead of spending quota again for
      data already in place. Load timestamp recorded via
      `ops.log_run(..., status="dev-fixture")` (adjustment 1) rather
      than a new table: reuses `ops.pipeline_runs` with a status value
      distinct from `"success"`/`"failed"`, so
      `estimate_next_run_setlistfm_cost()`'s `status='success'` filter
      ignores it (doesn't skew the real budget estimate) while
      `sum_setlistfm_requests_today()` still counts it (the requests
      were real). `dbt/README.md` (new, minimal — expands in item 5)
      states the data is temporary and gives the exact truncate command.
      **Verified for real**: ran the script against local Postgres —
      loaded 958 setlists/13,170 entries (matches spec-01 item 25's
      numbers exactly), MusicBrainz step correctly skipped (0
      requests), `ops.pipeline_runs` shows the `dev-fixture` row with
      timestamp, request counts and `setlists_per_band`.
- [x] **2. dbt project scaffold** — `dbt/dbt_project.yml`,
      `dbt/profiles.yml`. `profiles.yml` has zero literal credentials —
      every connection value is `env_var(...)` except `dbname: encore`
      (a fixed application constant, not a secret, matching
      `encore.db.DATABASE_NAME`) and `schema: staging` (the harmless
      default; every model's real schema is set per-layer in
      `dbt_project.yml`, see below). Verified nothing secret is in the
      repo by reading the committed file back — plain `env_var()` calls
      only (adjustment 2).
      `dbt/macros/generate_schema_name.sql` overrides dbt's default
      schema-naming (which would otherwise concatenate the profile's
      target schema with each custom schema, e.g. `staging_analytics`
      instead of `analytics`) — needed for `dbt_project.yml`'s
      per-layer `+schema:` config (staging/intermediate = view,
      analytics = table) to produce the exact schema names in
      `structure.md`. `models/`, `seeds/`, `tests/` directories are not
      pre-created empty (git doesn't track empty dirs; dbt doesn't
      require them to pre-exist) — they'll appear with their first real
      file in items 4/6/7.
      **Verified for real**: `dbt debug` (via the Docker image's
      `/opt/dbt-venv/bin/dbt`, `dbt/` mounted since it isn't copied into
      the image until item 19) connects successfully to the real
      `encore` database.
- [x] **3. Enable the `unaccent` Postgres extension** —
      `infra/postgres/init/03_create_unaccent_extension.sh` (adjustment
      3: `CREATE EXTENSION` needs superuser; only runs on an empty
      volume, same limitation as items 2/6 in spec-01). The dbt
      `on-run-start` hook (`dbt/macros/assert_unaccent_extension_exists.sql`,
      wired in `dbt_project.yml`) only checks the extension exists and
      raises a clear compiler error if it doesn't — it never tries to
      create it.
      **Verified both states for real** against the dev Postgres (which
      predates this script, so the init-on-empty-volume path couldn't
      be exercised directly): ran the macro via `dbt run-operation
      assert_unaccent_extension_exists` *before* the extension existed
      → failed with the exact intended message; created the extension
      manually (`CREATE EXTENSION IF NOT EXISTS unaccent`); re-ran the
      same command → passed silently. Note: `dbt run`/`build` currently
      report "Nothing to do" and skip `on-run-start` hooks entirely
      since there are still zero models/seeds — the hook only actually
      fires once item 4+ gives dbt something to run.
- [x] **4. Seeds** — `dbt/seeds/seed_album_exclusions.csv` (5 rows) and
      `dbt/seeds/seed_song_overrides.csv` (header only). The exclusion
      titles are the exact strings from the Phase 0 notebook's
      `ALBUNS_EXCLUIR` dict (not retyped from the spec's prose
      descriptions, which are paraphrases — e.g. the spec says "Oasis
      Manchester 1994" but the real MusicBrainz title is
      `Definitely Maybe Tour - 1994-12-18 - Manchester Academy -
      Homedown Showdown`); the Avenged Sevenfold one contains commas so
      it's quoted in the CSV. `dbt_project.yml` now pins every seed
      column to `text` explicitly: dbt infers seed types from the data,
      so a title like "1984" would silently become an integer, and the
      overrides seed is empty (header only) so inference has nothing to
      work from.
      **Verified for real**: `dbt seed` → `INSERT 5` and `INSERT 0`;
      `information_schema` confirms every column is `text`; a join of
      the exclusions against `raw_musicbrainz.albums` shows both Oasis
      titles match exactly 1 real album each (the Muse/A7X/Metallica
      ones show 0 only because those bands aren't loaded yet).
      **Also resolved the item-3 pending note**: this `dbt seed` run is
      the first one with something to run, and the `on-run-start` hook
      fired for real (`1 of 1 OK hook: encore.on-run-start.0`).
- [x] **5. `dbt/README.md`** — layout/schema table, prerequisites
      (including the `unaccent` caveat for databases that predate the
      init script), how to run dbt locally via the Airflow image's
      `/opt/dbt-venv` (dbt isn't in the project venv), and the
      dev-fixture section from item 1. The "inside Airflow" section
      says explicitly that it is **not wired up yet** (items 19-20)
      rather than describing behaviour that doesn't exist; revisit in
      item 20.
      **Verified by executing the README, not just writing it** — and
      that caught two bugs in my first draft: (1) `dbt debug` exited 2
      because it doesn't accept `--target-path` (only some subcommands
      do), so artifact redirection moved to the `DBT_TARGET_PATH` /
      `DBT_LOG_PATH` env vars, which work for every subcommand; (2)
      dbt kept dropping a `.user.yml` (anonymous-user id) into `dbt/`
      next to `profiles.yml`, fixed with
      `DBT_SEND_ANONYMOUS_USAGE_STATS=false`. Final check extracted the
      `dbt()` function verbatim from the committed README with `awk`
      and ran `debug`/`seed`/`run`/`test` through it: all exit 0, and
      `dbt/` contains only tracked files afterwards. (`run` and `test`
      exit 0 with "Nothing to do" until models exist in item 7.)
- [x] **6. `normalize_title(column)` macro** —
      `dbt/macros/normalize_title.sql`. Per adjustment 4 there is no
      `unit_tests:` block (those apply to models): the macro is exercised
      by `dbt/models/staging/test_fixtures/test_normalize_title_cases.sql`
      (25 literal inputs with hand-written expected outputs, plus the
      macro's `actual_title`) and the singular test
      `dbt/tests/assert_normalize_title_expected_outputs.sql`, which
      returns any row where `actual_title is distinct from
      expected_title` (`is distinct from` so NULL -> NULL compares
      equal). The macro builds its expression one rule per Jinja
      variable, in this order: lowercase+unaccent, apostrophes removed
      without a space, `&` -> `and`, edition segments dropped, trailing
      `feat.` clause dropped, remaining punctuation -> space,
      whitespace collapsed. (My first version was one deeply nested
      call and I miscounted the parentheses by hand — rewritten as
      stepwise variables before it ever ran.)
      **Verified for real, and the test itself verified**: `dbt run` +
      `dbt test` passed; read back all 25 actual outputs from the view
      (not just the pass/fail); then injected a regression (apostrophes
      -> space instead of nothing) and confirmed the test FAILS with 5
      rows, then restored the macro (`diff` against the backup empty)
      and confirmed it passes again. Caveat found doing that: the two
      `Rock 'n' Roll Star` cases still pass under the regression (the
      extra space collapses to the same string), so they don't actually
      discriminate the "no space" rule — the five other apostrophe
      cases (`Don't` x2, `Editor's`, `What's`, `Ain't`) do.
- [ ] **7. `stg_setlists`** — `dbt/models/staging/`.
- [ ] **8. `stg_setlist_entries`** — medley split via
      `string_to_array` + `unnest WITH ORDINALITY`.
- [ ] **9. `stg_albums` + `stg_album_tracks`** — album exclusions
      applied via anti-join against the seed.
- [ ] **10. `stg_recordings`** — deduplicated by `normalize_title(title)`,
      earliest `first_release_date` wins.
- [ ] **11. Staging schema tests** — `not_null`/`accepted_values` in
      `dbt/models/staging/schema.yml` (R7.1).
- [ ] **12. `int_song_catalog`** — `dbt/models/intermediate/`.
- [ ] **13. `int_performances`** — excludes tape/cover, seed overrides
      take precedence over automatic matching, `is_matched` flag.
- [ ] **14. `mart_repertoire_age`** — `dbt/models/analytics/`, grain
      band/tour/year, no `setlist_id`/`show_date`/`venue`/`song_name_raw`.
- [ ] **15. `mart_match_quality`** — grain band/year.
- [ ] **16. Singular test: no forbidden columns in `analytics`** (R7.2).
- [ ] **17. Singular test: `avg_repertoire_age` never negative** (R7.3).
- [ ] **18. Singular test: `match_rate` between 0 and 1** (R7.4).
- [ ] **19. `dbt/` copied into the Airflow image** —
      `airflow/Dockerfile`: `COPY dbt/ /opt/airflow/dbt/`.
- [ ] **20. Real `transform` task in `encore_pipeline`** — replaces the
      placeholder with `dbt seed`/`run`/`test` via
      `/opt/dbt-venv/bin/dbt`, before `cleanup_raw_setlistfm`; a dbt
      failure fails the task/DAG, cleanup still runs
      (`trigger_rule=all_done`, unchanged).
- [ ] **21. `notebooks/01_first_kpi.ipynb`** — reads only from
      `analytics`; line chart (repertoire age by year per band), bar
      chart (by tour for one band), match-quality table; outputs
      cleared before commit.
- [ ] **22. Acceptance run** — `ENCORE_BANDS_FILTER=Oasis`, full DAG
      twice: `raw_setlistfm` empty, `mart_repertoire_age` populated,
      second run idempotent (same mart contents except `computed_at`),
      all dbt tests pass. Per adjustment 5: if
      `match_rate_by_performance` for Oasis is below 0.90, list the
      unmatched titles ordered by performance count and **stop for
      review** — do not fill `seed_song_overrides.csv` unilaterally.

## Decisions log

- **2026-09-18** — Note on adjustment 3's premise: in this project's
  current setup, `POSTGRES_USER` (`airflow`, used by both dbt and
  `encore.db`) is the official `postgres:16` image's bootstrap role,
  which the image grants `SUPERUSER` by default — so `CREATE EXTENSION`
  actually *would* succeed over the app's normal connection here.
  Implemented the init-script-only approach anyway, per the adjustment:
  it's correct defense-in-depth for a hardened/production setup with a
  restricted app role, and costs nothing to build now.
- **2026-09-18** — `dbt run`/`dbt build`/`dbt seed`/`dbt test` all
  print "Nothing to do" and skip project-level hooks (`on-run-start`)
  when the command's node selection is empty — with zero models/seeds
  so far, there's nothing to validate the hook wiring against except by
  calling the macro directly via `dbt run-operation
  assert_unaccent_extension_exists`. Re-verify the hook fires as part
  of a normal `dbt run` once item 7 (`stg_setlists`) exists.
  **Resolved during item 4**: the first `dbt seed` run had seeds to run
  and the hook fired (`1 of 1 OK hook: encore.on-run-start.0`), and it
  fires on every run since.
- **2026-09-18** — **Interpretation call in `normalize_title` (item 6),
  flagged rather than silently chosen.** R3.1 says to "strip suffixes
  such as remastered, live, demo, edit, and `feat.` segments" while also
  saying it implements "the Phase 0 rules" — but Phase 0's actual rule
  (spec-01 R11.1(c)) deleted *all* bracketed content. Those two
  readings conflict. I implemented the keyword-based one: only a
  `(...)`/`[...]` group, or text after a `" - "`, that contains one of
  `remaster(ed)|live|ao vivo|demo|edit|feat|ft|featuring|single|bonus|
  NNNN version` (whole words) is dropped. Why: deleting every
  parenthesis would turn `(What's the Story) Morning Glory?` into
  `morning glory` and merge `Song (Part 1)` with `Song (Part 2)`. Cost:
  a mismatch like `Morning Glory` (setlist.fm) vs `(What's the Story)
  Morning Glory?` (MusicBrainz) is not fixed by normalization and must
  show up in `mart_match_quality` and be fixed via
  `seed_song_overrides.csv`. The keyword list is Phase 0's list plus
  `demo` and `edit` from the spec. Cheap to flip if the 0.90 gate in
  item 22 says recall is too low — but that is a call for review, per
  the adjustment-5 stop rule, not for me to tune quietly.
- **2026-09-18** — Test-fixture model placement (item 6): put
  `test_normalize_title_cases` in `models/staging/test_fixtures/` so it
  inherits the staging view config instead of adding a fourth layer
  folder to `dbt_project.yml`. Consequence: it builds as a real view,
  `staging.test_normalize_title_cases`, in the database on every full
  `dbt run` (harmless — literal values only).
