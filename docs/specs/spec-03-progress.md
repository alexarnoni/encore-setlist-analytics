# Spec 03 — Progress and implementation plan

Tracks `docs/specs/spec-03-rotation-survival.md` (rotation and song survival).
Same discipline as spec 01 and 02a: small tasks, one commit each, results
recorded here.

> **STATUS: PLAN APPROVED 2026-09-21 — implementation of T0-T13 in progress.**
> Work happens only on the branch `spec-03`, in the worktree
> `D:\projetos\encore-spec03`. T14 (merge and real-data run) waits for the
> main branch's next full run and its checklist. The running main stack,
> its image and containers are not touched.

## 1. Guardrails

The spec says: branch `spec-03`, no merge until the next full pipeline run on
the main branch has passed its checklist, no setlist.fm requests (synthetic
data in a disposable database), and no change to the main branch's image, DAG
or dbt models. Checking the repository turned up four ways to break that by
accident; each has a mitigation built into the plan.

| # | Hazard found | Mitigation |
|---|---|---|
| 1 | `.env` sets `AIRFLOW_IMAGE_NAME=encore-airflow:3.3.2`, the tag the running stack uses. Building from the branch with the default command would overwrite the main image. | Branch images are always built with an explicit tag, `encore-airflow:spec-03`, via `docker build -t`. `docker compose build/up` is never run from the branch. |
| 2 | `airflow/dags` is bind-mounted **from the working tree** into the running scheduler. Editing the DAG on the branch in the main directory would put the branch's DAG in front of the main stack (and it would import code the main image does not have). | Work in a separate **git worktree** (`D:\projetos\encore-spec03`, branch `spec-03`). The main directory stays on `master`. (D2) |
| 3 | The next checklist rebuilds the image *from the working tree*. If the main directory were on `spec-03` at that moment, the spec-03 code would be baked into main's image. | Same as 2: the main directory is left on `master` and the plan never switches it. |
| 4 | The Airflow image runs pandas 3.0.5 / numpy 2.5.3 / scipy 1.18.1; the project venv has pandas 2.2.3. Tests that pass on the host can fail in the image. | Survival and dbt-adjacent tests are also run **inside the branch image** (`docker run`), not only in the host venv. |

Also: dbt is only ever run against a disposable database (`encore_spec03`),
never `dbt run` / `dbt seed --full-refresh` on the real `encore` (with
`raw_setlistfm` empty it would wipe the real marts). The disposable database
gets the MusicBrainz tables copied from the real one (read-only copy) plus
synthetic setlists.

## 2. Facts checked while planning (2026-09-21)

- **lifelines fits the Airflow image.** `pip install --dry-run --constraint
  <Airflow 3.3.2 constraints> lifelines` resolves to `lifelines 0.30.0` (plus
  autograd, autograd-gamma, formulaic, interface-meta, matplotlib and its
  dependencies) without touching numpy/scipy/pandas. A real Kaplan-Meier fit
  in a throwaway container of the current image (pandas 3.0.5, numpy 2.5.3)
  produced the survival function, 95 % confidence interval, median and event
  table correctly. Nothing was installed in the image itself.
- **Data available to the models.** `int_performances` already excludes tape
  and covers and carries `setlist_id`, `band`, `show_date`, `tour_name`,
  `title_normalized` (canonical key after aliases), `song_title`,
  `reference_album`, `release_year`, `catalog_source`, `is_matched`,
  `is_medley`. `stg_setlists` has `show_date` (NULL when unparseable).
- **Forbidden-columns test** (`assert_no_forbidden_columns_in_analytics`) reads
  `information_schema` for the whole `analytics` schema, so it covers new marts
  automatically; it only needs new names added (requirement 14).
- **A contradiction to fix:** the header of `dbt/models/analytics/schema.yml`
  says nothing in `analytics` may carry a "song title", but spec 03 requires
  `song_title` in `mart_song_survival` (and `docs/context/product.md` allows
  aggregation "by song"). The header wording is corrected; the real rule (no
  show key, date, venue or raw title) stays.
- **Test placement problem (see D1):** the survival marts are written by Python
  *after* `transform`, but `transform` runs `dbt test` on everything. Tests on
  those marts cannot run there.
- Not yet checked: linux/arm64 wheels for the new dependencies (task T11).

## 3. Design points for approval

**D1 — Where the survival tests run.** The survival marts do not exist (or are
last run's) while `transform` executes `dbt test`, and the reconciliation test
(req. 15) needs `int_performances`, i.e. raw data, which is gone after
cleanup. Proposal: tag the survival tests `survival`; `transform` runs
`dbt test --exclude tag:survival`; the new `analyze` task runs the Python
module and then `dbt test --select tag:survival`, all before
`cleanup_raw_setlistfm`. A failing survival test fails `analyze` and so the DAG;
cleanup still runs (`all_done`, unchanged). This changes the command in
`src/encore/dbt_runner.py` (on the branch only).

**D2 — Isolated workspace.** Create the worktree
`D:\projetos\encore-spec03` on branch `spec-03`; copy `.env` into it (it is
gitignored); reuse the main `.venv` interpreter with `PYTHONPATH` pointing at
the worktree's `src`.

**D3 — Branch image and containers.** `docker build -t encore-airflow:spec-03`
from the worktree; run everything in throwaway `docker run` containers on the
existing network against the disposable database. No `compose up` from the
branch, so the running main stack is not restarted or touched.

**D4 — Ownership of the survival tables.** The Python module owns the DDL of the
three survival marts (create if not exists) and refreshes them in one
transaction (delete + insert), so a failed run keeps the previous content and a
rerun is idempotent; dbt only documents them as **sources** (req. 11) and tests
them. `computed_at` is set by the module.

## 4. Open questions (answer before the tasks that depend on them)

Each has a recommended default so work can start; a different answer costs a
small change, not a redesign. **The final answers are in section 4a; where they
differ from the defaults below (Q1, Q2, Q3, Q4, Q5), 4a wins.**

| # | Question | Recommended default | Affects |
|---|---|---|---|
| Q1 | **Duration convention.** The spec says "shows from live debut to the last appearance". Index difference or inclusive count? | `last_index - debut_index` (shows elapsed since debut); censored: `end_index - debut_index`. One constant, same rule for events and censoring. | T6 |
| Q2 | **Exact abandonment rule.** | After an appearance at index *i*, abandonment needs *N* consecutive later shows without the song, all inside the history: internal gap `>= N`, or tail `total_shows - last_index >= N`; otherwise censored (matches "fewer than 50 shows before the end"). First such gap only; the song is flagged `returned_after_abandonment` if it appears again. | T6 |
| Q3 | **Which year a pair belongs to** in `mart_band_rotation_by_year` (a pair can straddle New Year inside a tour), and whether tours excluded for `< 5 shows` are also excluded there. | Year of the **later** show of the pair; excluded tours are excluded from the yearly mart too. | T5 |
| Q4 | **Jams, solos, generic entries.** `product.md` excludes them from catalog KPIs, but the data has no jam flag and earlier we chose to leave matching artifacts as they are (e.g. `Helpless (jam)` is a recording-only catalog song). They would count as songs in set sizes, Jaccard and survival. | Include as-is (spec text), record as a limitation in `docs/methodology.md`; no new filter. | T2, T6 |
| Q5 | **Eligible songs.** "Catalog songs with at least 3 performances" also admits recording-only songs (label `non-album`), some with no release year and some being bootleg-style entries; the decision on undated recordings is still open until the next run's numbers. | Follow the spec literally (>= 3 *performances*, `release_year` nullable in the mart); revisit after the run. | T6, T8 |
| Q6 | **Minimum size for a Kaplan-Meier curve** per band and album (an album with 2 songs gives a meaningless confidence band). The spec sets none. | No threshold in the marts (they carry `songs`); the notebook only draws albums with `>= 5` songs. | T7, T12 |
| Q7 | **Time grid `t_shows`.** | The Kaplan-Meier timeline (the distinct event and censoring times) plus `t = 0`, not every integer. | T7 |
| Q8 | **Two shows with the same date** (double shows, festival sets) — order within a band and within a tour. | Tie-break by `setlist_id`: deterministic, arbitrary; documented. Undated shows cannot be ordered and are left out of pairs and of the show index (their number is logged). | T2, T3, T6 |
| Q9 | **"Performances" vs distinct shows** for eligibility: a song played twice in one show has 2 performances but 1 show. | Eligibility uses performances (spec wording); durations use distinct shows. | T6 |

Sanity checks from the spec (Metallica vs Muse rotation in recent tours,
debut-album songs censored, N-window results not drastically different) can
only be judged on **real data**, i.e. after the branch is merged and a full
pipeline run has produced the marts (T14). Until then the plan proves the
*mechanics* with synthetic histories whose answers are known by construction.

## 4a. Decisions (approved 2026-09-21) — these win over the defaults in section 4

- **D1-D4 approved** as proposed. D2: worktree `D:\projetos\encore-spec03`
  (branch `spec-03`); the main directory stays on `master`. D3: branch image
  tag `encore-airflow:spec-03`. **Refinement of the disposable database
  (T0):** instead of creating a database inside the running stack's Postgres,
  spec-03 gets its **own container** `spec03-postgres` (own Docker network,
  published on `127.0.0.1:5446` only). From inside it the real `postgres`
  service is not even resolvable, so no dev command can reach the real
  database by accident. The database is called `encore`, so the unchanged
  dbt profile and `encore.db` work by only changing `POSTGRES_HOST`.
- **Q1 / Q2 (changed from the default).** Duration is measured **in band
  shows from the live debut to the last appearance before the gap,
  inclusive**: `last_index - debut_index + 1`, so a song played in one show
  has duration 1. A censored song uses the same rule up to the end of the
  history: `total_shows - debut_index + 1`. Abandonment: **absent from the
  next N shows** (N = 25, 50, 100) after an appearance, all inside the
  history: an internal gap of `>= N` shows, or `total_shows - last_index >= N`
  at the tail; otherwise censored. Only the first abandonment counts; the
  song is flagged `returned_after_abandonment` if it appears again.
- **Q3.** A pair belongs to the **year of its second show**. Tours excluded
  for fewer than 5 shows are excluded from the yearly mart as well.
- **Q4 / Q5 (for now, revisit after the next run's numbers).** Survival
  eligibility: at least 3 performances **and** the song is matched to a
  studio album (`reference_album` not null) **or** to a recording that has a
  release year (`release_year` not null). Recording-only songs without a
  release year are not eligible. Recording-only songs with a year are
  eligible under the album label `non-album`. Jams, solos and other generic
  entries are included as they are (no filter); recorded as a limitation.
  *Rotation is unaffected:* setlist sets contain every matched song, as the
  spec says.
- **Q6-Q9 (recommended defaults, accepted).** Q6: no minimum group size in
  the marts (they carry `songs`); the notebook draws only albums with at
  least 5 songs. Q7: the time grid is the Kaplan-Meier timeline (event and
  censoring times) plus `t = 0`. Q8: same-date shows are ordered by
  `setlist_id`, shows without a date are left out of pairs and of the show
  index. Q9: eligibility counts performances, durations use distinct shows.
- **Conventions fixed while planning.** "Performances" of a song means its
  matched performances in shows with a known date (the same population as the
  show sets), so the reconciliation test (req. 15) and the module use one
  definition. The album label `non-album` is used in `mart_song_survival`
  too (not only in the curves), so the marts join on the same label. The
  survival module derives eligibility from the raw counts in Python while the
  reconciliation test re-derives it in SQL, so the test is not a tautology.

## 5. Ordered tasks

Every task ends with the tests run, a commit, and an entry here. Verification
always includes an **independent recomputation** (plain Python from the
synthetic raw rows, not through the models under test) and a **mutation check**
(break the code on purpose, see a test go red, restore, `diff` clean), as in
spec 02a.

**Synthetic data (used from T1 on).** Deterministic histories with known
answers: *fixed* (same set every show: rotation 0, all songs core), *alternating*
(two disjoint sets: rotation 1), *known overlaps* (hand-computed Jaccard),
*M72-like* (per city two different sets), tours with fewer than 5 shows,
`Unknown tour`, an undated show, same-date shows, a 15-year hiatus, songs
abandoned exactly at the window / one show short / censored / returning, songs
with fewer than 3 performances, recording-only songs (`non-album`), several
bands. Plus one larger seeded random history checked against the Python oracle.

| Task | What | Files touched | How it is verified |
|---|---|---|---|
| **T0** | Workspace: worktree, `.env` copy, `encore_spec03` create/drop helper | `scripts/spec03/scratch_db.sh` (new) | `git worktree list`; main directory still on `master` with a clean tree; `docker images` shows `encore-airflow:3.3.2` unchanged (same image id before/after); main scheduler still lists no DAG import errors |
| **T1** | Synthetic history builders (pure Python, with the expected answers) and a loader into the disposable DB's `raw_setlistfm` | `tests/support/histories.py` (new), `scripts/spec03/load_synthetic.py` (new) | Unit tests on the builders (counts, dates, determinism); loader run into `encore_spec03`; loaded row counts equal the builders' |
| **T2** | `int_show_song_sets` view: one row per show and canonical matched song (`show_key`, band, `tour_name`, `show_date`, `song_key`), distinct, dated shows only | `dbt/models/intermediate/int_show_song_sets.sql`, `.../schema.yml` | Sets equal the oracle's for every synthetic show; singular test: unique `(show_key, song_key)`; not_null; tape/covers/unmatched absent; mutation (drop the `is_matched` filter, drop `distinct`) caught |
| **T3** | `int_show_pairs` view: consecutive pairs per band + tour (date, then `setlist_id`), `Unknown tour` excluded, Jaccard | `dbt/models/intermediate/int_show_pairs.sql`, `dbt/models/staging/test_fixtures/test_jaccard_cases.sql`, `dbt/tests/assert_jaccard_expected_outputs.sql`, schema | **Req. 13:** fixture model with known sets + singular test of expected values (identical = 1, disjoint = 0, 2 of 3 = 0.5 …); pairs equal the oracle on all scenarios; a tour of *n* shows has *n-1* pairs; mutations (wrong ordering, union computed as sum) caught |
| **T4** | `mart_tour_rotation` (grain band + tour): shows, pairs, mean Jaccard, rotation, median set size, core songs (>= 90 % of shows), distinct songs; tours with < 5 shows excluded | `dbt/models/analytics/mart_tour_rotation.sql`, `.../schema.yml`, `dbt/tests/assert_mart_tour_rotation_*.sql` | Values equal the oracle on all scenarios (fixed = 0, alternating = 1, hand-computed overlap); rotation in [0, 1]; unique grain; small and `Unknown` tours absent; no forbidden columns; mutations (threshold 5 -> 4, core 90 % -> 80 %) caught |
| **T5** | `mart_band_rotation_by_year` (grain band + year, weighted by pairs) — depends on Q3 | `dbt/models/analytics/mart_band_rotation_by_year.sql`, schema, tests | Equals the oracle; pair counts per year sum to the pairs of `mart_tour_rotation`; consistency test between the two marts; mutations caught |
| **T6** | Survival core, pure Python: show index, per-song appearances, duration / event / censoring for N = 25, 50, 100, `returned_after_abandonment`, eligibility — depends on Q1, Q2, Q5, Q9 | `src/encore/analysis/__init__.py`, `src/encore/analysis/survival.py` (new), `tests/test_survival.py` (new) | **Req. 12** hand-built histories: abandoned exactly at the window, one show short of it (not abandoned), censored, returns after abandonment (first event only, flagged), long calendar hiatus with no false abandonment, < 3 performances ineligible, results differ across N; mutations (`>=` -> `>`, off-by-one in duration, counting calendar time) caught; run on host **and** in the branch image |
| **T7** | Kaplan-Meier curves and summary with lifelines per band and per band + album (`non-album`, `all`), N = 25/50/100: at risk, events, probability, confidence interval, median (null if the curve never reaches 0.5) — depends on Q6, Q7 | `src/encore/analysis/survival.py`, `tests/test_survival_km.py` | Compared with an independent hand-written product-limit estimator on small datasets (and with the earlier smoke-test numbers); non-increasing and in [0, 1]; median null case; `events + censored = songs`; in the branch image (pandas 3) |
| **T8** | Database I/O: read the show sets and song attributes, create and refresh `mart_song_survival`, `mart_survival_curves`, `mart_survival_summary` in one transaction; years only, no dates | `src/encore/analysis/survival.py` (or `io.py`), `src/encore/analysis/__main__.py` | End to end on `encore_spec03`: marts equal an independent recompute from raw; idempotent (identical md5 excluding `computed_at`); atomic (an injected failure mid-write leaves the previous content); no date, show key or raw title in any column |
| **T9** | dbt sources and tests for the survival marts, tagged `survival`; forbidden-columns list extended (`show_key`, `show_id`, `show_index`, `setlist_url` in addition to today's four); analytics `schema.yml` header corrected | `dbt/models/analytics/survival_sources.yml`, `dbt/tests/assert_survival_*.sql`, `dbt/tests/assert_no_forbidden_columns_in_analytics.sql`, `dbt/models/analytics/schema.yml` | **Reqs. 11, 14, 15:** probability in [0, 1] and non-increasing per curve; `events + censored = songs`; grain uniqueness; reconciliation `mart_song_survival` songs per band = eligible catalog songs in `int_performances`; each test proven red by mutating a mart |
| **T10** | Wire it in: `analyze` task between `transform` and cleanup; `transform` excludes `tag:survival`; `run_analyze()`; `log_run` knows the new step | `airflow/dags/encore_pipeline.py`, `src/encore/dbt_runner.py`, `tests/test_dbt_runner.py`, new `tests/test_analyze.py` | Unit tests: order, `analyze` failure fails the run, cleanup still runs; the branch DAG imports cleanly and the task graph / trigger rules are asserted inside the branch image (`docker run`, dags folder mounted from the worktree); `analyze` run against `encore_spec03` |
| **T11** | Image: `lifelines` in `airflow/requirements.txt` (and the root `requirements.txt`); build `encore-airflow:spec-03` | `airflow/requirements.txt`, `requirements.txt`, (`airflow/Dockerfile` only if needed) | Build succeeds under the Airflow constraints; the smoke test passes in the built image; size delta reported; **linux/arm64:** every new wheel checked with `pip download --platform manylinux2014_aarch64 --only-binary=:all:`; main image id unchanged |
| **T12** | Notebook `notebooks/02_rotation_survival.ipynb`: rotation by year (small multiples, same y scale), Kaplan-Meier curves for one band with a line per album and confidence bands, median-survival table for N = 50; reads only `analytics` | `notebooks/02_rotation_survival.ipynb` (the DB name becomes configurable so it can read the disposable database) | Executed against the synthetic marts, charts inspected (dataviz skill); committed with 0 outputs; the executed HTML goes to gitignored `reports/`; read-only session and table whitelist as in notebook 01 |
| **T13** | Docs: definitions and limitations in `docs/methodology.md` (rotation, core songs, survival conventions, Q4/Q5 caveats), `dbt/README.md` (`analyze`, survival tests), README architecture, `structure.md` (`src/encore/analysis/`) | the docs listed | Read-through against the code; every convention chosen in Q1-Q9 stated |
| **T14** | **Merge gate and real-data validation** (after the main branch's next full run passed its checklist): merge `master` into `spec-03`, merge to `master`, rebuild the main image, full pipeline run, then acceptance | (no new code expected) | All new marts populated, dbt tests pass, `raw_setlistfm` empty; spec sanity checks on real data (Metallica vs Muse rotation in recent tours; debut-album songs censored with long durations; N = 25/50/100 differ but not drastically), or the deviation is explained; costs one more full run (~481 setlist.fm requests) |

## 6. What can be done now, and what should wait

**Can be done now (no quota, nothing on the main branch touched):** T0-T13,
all on synthetic data in the disposable database, in the worktree, with
`encore-airflow:spec-03`. The unknowns that could block T6-T9 are the answers
to Q1-Q9; the recommended defaults let work start without them.

**Should wait:**
- **The merge (T14) waits for tomorrow's main run** and its checklist (the spec
  makes that a hard gate), and the run itself waits until after 18:10 UTC.
- **Real-data sanity checks wait for a run after the merge.** Tomorrow's run
  produces no spec-03 marts (the code is not on `master`), and another full run
  costs ~481 requests, so it cannot be the same day.
- **Q5 depends on tomorrow's numbers** (share of matched performances without a
  release year and the two title lists): they show how much recording-only noise
  the "eligible songs" rule lets into the survival analysis.
- **Nothing that rebuilds or restarts the main stack** (image, containers, DAG
  folder) until after tomorrow's checklist.

## 7. Checklist

- [x] Plan approved (D1-D4, Q1-Q9 answered or defaults accepted) — section 4a
- [x] T0 workspace and guardrails
- [x] T1 synthetic histories
- [x] T2 `int_show_song_sets`
- [x] T3 `int_show_pairs` + Jaccard test
- [x] T4 `mart_tour_rotation`
- [ ] T5 `mart_band_rotation_by_year`
- [ ] T6 survival core + unit tests
- [ ] T7 Kaplan-Meier curves and summary
- [ ] T8 database I/O and the three marts
- [ ] T9 dbt sources, tests, forbidden columns
- [ ] T10 `analyze` task and runner
- [ ] T11 image with lifelines (arm64 checked)
- [ ] T12 notebook
- [ ] T13 documentation
- [ ] T14 merge gate, full run, real-data sanity checks

## 8. Decisions log

- **2026-09-21** — Spec file moved to `docs/specs/spec-03-rotation-survival.md`
  (it had been dropped in the repository root) and committed on `master`
  (docs only) so that the branch starts from it. The `spec-03` branch was
  created from it; the plan is the first thing committed on the branch.

## 9. Task log

### T0 — workspace and guardrails (done)

Worktree `D:\projetos\encore-spec03` on `spec-03`; `.env` copied in (gitignored).
`scripts/spec03/env.sh` (helpers `s3psql`, `s3dbt`, `s3py`, `s3hostenv`),
`up.sh` (starts or resets the isolated Postgres, copies the real MusicBrainz
tables read-only through a throwaway `pg_dump` container, creates the empty
`raw_setlistfm` tables with the project's own DDL) and `down.sh`;
`.spec03-local/` (the cached MusicBrainz dump) is gitignored.
**Verified.** Snapshot of the main stack before and after: identical image id
(`0d38653fa85a`), container ids and creation times, main directory on `master`
with a clean tree, no DAG import errors, real marts still 404 rows. From a
container on the spec-03 network the real `postgres` service is not
resolvable, while `spec03-postgres` is; `dbt debug` connects to it
(`host: spec03-postgres`) and `dbt seed` + `dbt run` build all 14 existing
models from the copied MusicBrainz data (4,843 catalog songs across the 7
bands). The dbt and Python helpers only ever `docker run` from the current
image; nothing is rebuilt or retagged.

### T1 — synthetic histories, oracle and loader (done)

`tests/support/histories.py` (deterministic builders, one band per scenario so
results stay separable), `tests/support/oracle.py` (independent plain-Python
oracle: Jaccard, consecutive pairs, tour rotation, yearly rotation, show index,
literal "absent from the next N shows" abandonment, eligibility),
`tests/support/db.py` (song pools from the real catalog, insert helpers, and a
guard that **refuses any host other than `spec03-postgres`**),
`scripts/spec03/load_synthetic.py`, `tests/test_spec03_synthetic.py`.
Scenarios: Oasis (fixed / alternating / hand-computed overlap / short /
no-tour tours, two undated shows, same-date shows, a repeated song, covers and
tape and unmatched entries); Metallica (M72-like alternating sets across New
Year, plus a steady tour); Muse (260 shows with a 12-year calendar hiatus and
songs abandoned exactly at the window, one show short, censored, returning,
played across the hiatus, with 2 performances, recording-only with and
without a year); Arctic Monkeys (eligibility: 2 vs 3 performances, an undated
third play, two plays in one show, recording-only songs); Linkin Park (150
shows, seeded pseudo-random).
**Verified.** 24 unit tests against hand-derived values (Overlap Tour mean
Jaccard 109/210 from 3/5, 1/3, 1, 1/7; M72 Jaccard 1/5 with 5 core songs;
yearly split 10 pairs in 2022 and 24 in 2023 with the steady tour; the Muse
outcomes for N = 25, 50, 100 in a table). Writing them exposed three mistakes
of mine in the *expectations* (the hiatus is 12.5 years not 15, the 5 songs
common to both M72 sets are core, a song played once at show 7 of 100 is
abandoned with duration 1 not censored); the oracle was right each time and the
tests were corrected. Loaded into the spec-03 database through the raw tables:
536 setlists and 3,793 entries (104 covers, 104 tape entries), equal to what
the builders produce per band; the real database was not touched (0 raw rows).

### T2 — `int_show_song_sets` (done)

`dbt/models/intermediate/int_show_song_sets.sql` (view; `show_key`, band,
`tour_name` with `Unknown tour`, `show_date`, `song_key`, `song_title`;
distinct matched songs of dated shows), schema entry, singular tests
`assert_int_show_song_sets_unique_key` and
`assert_int_show_song_sets_only_catalog_songs` (checks against
`int_song_catalog` directly, not through the flag the model uses), and
`tests/spec03/` (DB-level tests against the oracle, opt-in with
`SPEC03_DB_TESTS=1`, see `tests/spec03/conftest.py`).
**Verified.** The set of every synthetic show equals the oracle's (536
setlists; undated shows, unmatched titles, covers and tape absent; one row per
show and song). Mutations, each restored: no `is_matched` filter (104 rows
fail the catalog test and `not_null song_title`; oracle fails), no `distinct`
(the repeated song in one show breaks uniqueness; oracle fails), undated shows
kept (11 rows fail `not_null show_date`; oracle fails).
**Performance finding (important).** The first version filtered
`int_performances` directly with `where is_matched`. At the size of a real run
(a generated dataset of about 7,000 setlists and 132,000 entries,
`scripts/spec03/scale_data.sql`, isolated database) it took **over 240 s**
(over 10 min in one measurement), against 4 s for `int_performances` without the
filter: the filter makes Postgres reorder the joins and re-evaluate the
`stg_setlists` view (date parsing) once per entry. The model now reads
`int_performances` through a `materialized` CTE and filters afterwards:
**6 s** at the same size. Every later spec-03 model reads `int_show_song_sets`
rather than filtering `int_performances` itself.
**Side finding on `master` (not touched):** the diagnostic report's
`UNDATED_SONGS_SQL` (`where is_matched and release_year is null ...`) took
**80 s** at that size (the other two report queries 2.9 s each), so the log
report adds roughly 90 s to tomorrow's `transform`. Not a hang and not a
correctness problem; a `materialized` CTE would remove it. Reported to the
project owner instead of changed, since `master` is off limits until the
checklist is done.

### T3 — `int_show_pairs` and the Jaccard test (done)

`dbt/macros/consecutive_show_pairs.sql` (the pair and Jaccard logic, taking any
relation of show sets), `dbt/models/intermediate/int_show_pairs.sql` (the macro
over `int_show_song_sets`), `dbt/models/staging/test_fixtures/test_jaccard_cases.sql`
(the same macro over literal sets), singular tests
`assert_jaccard_expected_outputs` (**requirement 13**: identical = 1,
disjoint = 0, 2 of 4, a chain where only adjacent shows pair, ordering by date
against the keys, same-date tie broken by key, a single show and `Unknown
tour` never paired; full outer join so a missing or extra pair fails) and
`assert_int_show_pairs_one_fewer_than_shows` (n shows give n-1 pairs, a chain
not a web, counted from `int_show_song_sets` directly), schema entry, and
`tests/spec03/test_show_pairs.py` against the oracle. The Oasis synthetic
history gained a "Reverse Tour" (6 shows whose ids descend while dates ascend).
**Verified.** All 17 dbt tests and 5 oracle tests pass; the pairs equal the
oracle's exactly (as fractions) for every synthetic tour. Mutations on the
macro: union computed as a plain sum (fixture test 7 rows, oracle fails), the
`Unknown tour` filter removed (fixture test, oracle fails), pairing with the
show two places later (fixture test, one-fewer test and oracle fail).
**A gap found and closed:** ordering by `show_key` alone (ignoring the date)
was caught by *nothing* at first, because in my fixture and my synthetic
histories the keys happened to run in date order. The fixture now uses keys
against the dates and the Reverse Tour was added; the same mutation now fails
the fixture test (2 rows) and the oracle. (The one-fewer test cannot see it,
by design: it only counts.) Two more of my own hand-derived expectations were
wrong and corrected (a disjoint pair is 0, not 1/5).
**Performance.** At production size (about 7,000 setlists and 132,000 entries,
`scripts/spec03/scale_data.sql`): `int_show_song_sets` 5.0 s,
`int_show_pairs` 6.1 s (6,207 pairs). The marts of T4 and T5 should read
these views once each.

## 10. Where things stand (end of day, 2026-09-21)

T0-T3 done; T4-T13 not started. Nothing of spec 03 is on `master`. The main
stack, image, containers and DAG folder were not touched (compared before and
after at T0: same image id, container ids and creation times). The main
directory is on `master` with a clean tree. The isolated `spec03-postgres`
container is stopped; `bash scripts/spec03/up.sh` brings it back with its data
(the volume is kept), then `python scripts/spec03/...` / `load_synthetic.py`
reload the synthetic histories if needed.
Open item for the project owner: the diagnostic report on `master` takes about
90 s at production size (see T2).

### T4 — `mart_tour_rotation` (done)

`dbt/models/analytics/mart_tour_rotation.sql` (grain band/tour_name: shows,
pairs, mean_jaccard, rotation = 1 - mean_jaccard, median_setlist_size,
core_songs — >= 90% of shows, exact-fraction comparison — distinct_songs,
first_year/last_year), schema entry, `assert_mart_tour_rotation_unique_grain`
and `assert_mart_tour_rotation_internal_consistency` (rotation formula and
bounds, pairs = shows - 1, shows >= 5, core <= distinct, no `Unknown tour`,
first_year <= last_year), and `tests/spec03/test_tour_rotation.py` against
the oracle. Tours with fewer than 5 shows and `Unknown tour` never get a row
(matches the oracle's design from T1): rotation cannot be measured on either.
**Caught while writing the schema:** a plain YAML scalar description
containing `(excluded: not a real tour)` broke dbt's parser — a colon+space
mid-string reads as a new mapping key. Quoted the string.
**Verified.** All values equal the oracle exactly (as rounded to 4 decimals)
for every synthetic tour; `Unknown tour` and Oasis's 4-show "Short Tour" are
absent; Metallica's M72-like tour has higher rotation than its steady tour
(the spec's real-data sanity check, reproduced on synthetic data). Mutations:
no minimum-shows filter (the consistency test AND the oracle both fail — the
oracle test even without needing the shows>=5 rule to be phrased the same
way, since it compares the full set of tours); core threshold 90% -> 50%
(**the dbt consistency test does not catch this** — core_songs <=
distinct_songs still holds — only the oracle test does, which is exactly why
it exists); rotation defined as `mean_jaccard` instead of `1 - mean_jaccard`
(both fail). All restored, model `diff` clean.
