# Spec 03 — Progress and implementation plan

Tracks `docs/specs/spec-03-rotation-survival.md` (rotation and song survival).
Same discipline as spec 01 and 02a: small tasks, one commit each, results
recorded here.

> **STATUS: T0-T14 done (2026-09-23), merged to master. Abandonment rule changed to the LAST gap on branch `spec-03` (not yet on master, not yet run on real data): see the T14 addendum — see section 11
> for exactly where to pick up.** Work happens only on the branch
> `spec-03`, in the worktree `D:\projetos\encore-spec03`. T14 (merge and
> real-data run) is explicitly on hold until the user asks for it. The
> running main stack, its image and containers are not touched.

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
- [x] T5 `mart_band_rotation_by_year`
- [x] T6 survival core + unit tests
- [x] T7 Kaplan-Meier curves and summary
- [x] T8 database I/O and the three marts
- [x] T9 dbt sources, tests, forbidden columns
- [x] T10 `analyze` task and runner
- [x] T11 image with lifelines (arm64 checked)
- [x] T12 notebook
- [x] T13 documentation
- [x] T14 merge gate, full run, real-data sanity checks (sanity check 2 deviates, explained)

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

### T5 — `mart_band_rotation_by_year` (done)

`dbt/models/analytics/mart_band_rotation_by_year.sql` (grain band/show_year;
pairs, mean_jaccard, rotation, weighted by pairs — every pair counts once
regardless of tour). A pair belongs to the year of its **second** show
(decision Q3). Only pairs from tours present in `mart_tour_rotation` are
counted (an inner join against it, not a re-filter of `int_show_pairs`), so
the two marts agree by construction rather than by coincidence. Schema entry,
`assert_mart_band_rotation_by_year_unique_grain`,
`..._internal_consistency` (rotation formula and bounds), and — new kind for
this pair of marts — `assert_rotation_marts_agree_on_pair_counts` (sum of
pairs per band must match between the two marts, full outer join so a
missing band fails too), plus `tests/spec03/test_band_rotation_by_year.py`.
**Verified.** Equals the oracle exactly for every band/year; Metallica's
M72-like tour (crossing New Year) splits into 10 pairs in 2022 and 24 in 2023
(19 from M72 + 5 from the Steady Tour), matching the T4 numbers and the
Q3 rule read literally. Mutations: grouping by the pair's *first* show instead
of the second — **not caught by any dbt test** (both marts still agree in
total pair count, since the pairs just move to different years within the
same band), only by the oracle; joining against `mart_tour_rotation` with a
LEFT join instead of INNER (so excluded-tour pairs leak in) — caught by both
`assert_rotation_marts_agree_on_pair_counts` and the oracle. Both restored,
model `diff` clean.

### Performance check, T4-T5, at production scale

Same ~7,000-setlist / ~132,000-entry synthetic dataset as T2-T3
(`scripts/spec03/scale_data.sql`). `mart_tour_rotation` 18.3 s (768 rows),
`mart_band_rotation_by_year` 6.5 s (253 rows); all 25 rotation-related dbt
tests pass at this size. Data removed afterwards, back to 542 synthetic rows.

**Part A (rotation) of spec 03 is complete: T2-T5 done.** Part B (survival,
T6-T9) is next.

### T6 — survival core in Python + unit tests (done)

`src/encore/analysis/__init__.py`, `src/encore/analysis/survival.py` (pure
Python, no database access): `band_show_index` (1-based position of each
distinct dated show, tie-broken by show_key per Q8), `song_appearance_indices`
(distinct show indices per song, deduplicating repeats within one show),
`is_eligible`/`eligible_songs` (>= 3 performances AND matched to an album or
a dated recording — Q4/Q5/Q9), `outcome_for_window` (the abandonment rule for
one song at one window N: the first in-history gap of N consecutive silent
shows after some appearance is the event, inclusive duration
`last_index - debut_index + 1`, else censored to the end of history —
decisions Q1/Q2), `compute_survival` (wires it all together for one band and
a tuple of windows, returning one `SongSurvival` per eligible, dated-and-
played song). `tests/test_survival.py` (requirement 12): hand-built
histories for a song abandoned exactly at the window (including the boundary
`appearance + window == total_shows`, off by one on each side), a song one
show short of it, a censored song, a song returning after its first
abandonment, only the first qualifying gap counting even when a later one
also qualifies, and a band with a 20-calendar-year hiatus played straight
through the boundary (no false abandonment from calendar time — the show
index has no gap there at all).
**Slips of mine, corrected while writing the integration test:** the first
"Exact" scenario accidentally included a later appearance that made it
"return"; the first "Short" scenario's internal gap of 4 turned out to still
end in a real abandonment later in the history (my hand count missed the tail
gap after its last appearance) — redesigned to sit near the end of history
where the tail is genuinely too short; the first "Hiatus" scenario (3
appearances, none afterwards) was in fact correctly abandoned by the rule,
not a bug — redesigned to play continuously across the hiatus boundary to
test what the scenario actually intends. In each case the code was right and
the hand-derived expectation was wrong.
**Mutations:** 9 tried, 1 initially uncaught — changing the gap's in-history
boundary from `<=` to `<` (missing an abandonment when the gap reaches
exactly the last show) passed all 16 tests unchanged. Added
`test_gap_exactly_reaching_the_end_of_history_still_counts` (boundary case
both ways); the mutation now fails it. All 10 mutations then caught: duration
off-by-one (debut side and censored side), the gap-length off-by-one, the
boundary just fixed, "returned" using `>=` instead of `>`, eligibility
ignoring the performance threshold, eligibility requiring both album AND year
instead of either, the show-index tie-break, and continuing past the first
qualifying gap instead of stopping. Restored, file `diff` clean. Full suite:
125 passed, 10 skipped (the skipped ones are `tests/spec03`'s DB-level tests,
opt-in with `SPEC03_DB_TESTS=1`).
**Not yet wired to real data:** this module does not yet read
`int_show_song_sets` or the catalog from the database (T8), and it does not
fit Kaplan-Meier curves (T7) — both come next.

### T7 — Kaplan-Meier curves and summary with lifelines (done)

Extended `src/encore/analysis/survival.py`: `SongSurvival` gained
`album_label` (the song's `reference_album`, or `NON_ALBUM` — set in
`compute_survival` from the same catalog info used for eligibility, so T6's
core and T7's grouping agree on what "the song's album" means).
`group_by_album` groups one band's outcomes into `ALL_ALBUMS` (every eligible
song) plus one group per album label including `NON_ALBUM` (requirement 6:
"per band, and per band and reference album"). `fit_curve` wraps
`lifelines.KaplanMeierFitter` for one (band, album, window) group: returns a
`CurvePoint` per distinct time on the KM timeline (at_risk, events,
probability, 95% CI) and a `CurveSummary` (songs, events, censored, median —
`None` when the curve never drops below 0.5, per Q6/spec wording). Verified
first, in an interactive session, that lifelines' `survival_function_` and
`event_table` share the exact same time index including `t = 0` at
probability 1.0 with everyone at risk — so Q7's time grid ("the KM timeline
plus t=0") needs no extra code, t=0 is already the first row.
`tests/test_survival_km.py`: a **hand-written product-limit estimator**
(Kaplan & Meier's own formula, not lifelines' algorithm) checked first
against a textbook no-censoring case (plain empirical survival), then
`fit_curve`'s probabilities compared against it on a 10-song dataset with
ties on both events and censoring — matches to 1e-9. Also: the curve starts
at t=0/probability 1/everyone at risk; non-increasing and each point's CI
brackets its probability; `events + censored == songs`; median `None` when
all-censored, set correctly when the curve does cross 0.5; an empty group
returns an empty curve and a `None` summary, not an error;
`group_by_album`'s grouping (all/per-album/non-album) on 4 songs, and on the
empty case.
**Mutations, all caught:** event flags inverted (fails the product-limit
comparison and both median tests); the `inf`-to-`None` conversion removed
(fails the "never drops below 0.5" test); `group_by_album` silently dropping
the non-album group (fails the grouping test); the two CI columns swapped
(fails the "CI brackets the probability" bound, since one bound ends up on
the wrong side). File restored, `diff` clean against the pre-mutation copy.
**A slip of mine, fixed before running anything:** the first draft of
`test_fit_curve_of_an_empty_group_is_a_flat_none` had a leftover, meaningless
`assert summary == pytest.approx if False else summary.songs == 0` line from
editing — removed; the real assertions were already there right after it.
**Dependency note (formalized properly in T11):** `lifelines` is not yet in
any `requirements.txt` or in the Airflow image. For now I installed it into
the shared host dev `.venv` only, so these unit tests can run today; T11
adds it to `airflow/requirements.txt` (and the root `requirements.txt` for
the notebook), rebuilds `encore-airflow:spec-03`, and checks arm64 wheels.
Full suite: 135 passed, 10 skipped (the `tests/spec03` DB-level tests, opt-in).
**Still not wired to real data:** `fit_curve`/`group_by_album` take
in-memory `SongSurvival` lists; reading `int_show_song_sets` and the catalog
from the database, and writing `mart_song_survival` /
`mart_survival_curves` / `mart_survival_summary`, is T8.

### T8 — database I/O and the three survival marts (done)

`src/encore/analysis/io.py`: `fetch_show_appearances` (from
`intermediate.int_show_song_sets`), `fetch_performance_counts` (matched,
dated performances per band/song from `intermediate.int_performances` — the
same population as the show sets, so eligibility and appearances agree),
`fetch_catalog` (from `intermediate.int_song_catalog`); `ensure_tables`
(idempotent `CREATE TABLE IF NOT EXISTS` for all three marts, same style as
`ops.ensure_tables`); `compute_marts_from_data` (pure: appearances +
performance counts + catalog -> the three marts' rows, no DB); `compute_all_marts`
(fetches then delegates to the pure function); `write_survival_marts`
(ensures tables, computes, then DELETE + INSERT for all three tables inside
one try block, `conn.rollback()` and re-raise on any failure — design
decision D4: a failed run leaves the previous content in place, and this is
what makes a rerun idempotent). `src/encore/analysis/__main__.py`:
`python -m encore.analysis`, the entry point T10's `analyze` task will call;
lets any exception propagate for the caller to turn into a failed task.
`mart_song_survival` uses window N=50 specifically for its own
`duration_shows_n50`/`event_n50`/`returned_after_abandonment` columns (the
"headline" single-window view — design choice recorded back in T7); the
curves/summary marts carry every window in `WINDOWS`. `debut_year`/`last_year`
are read from the real show dates at the debut/last show index (T7/T8 never
had year information; added `_show_years_by_index`, reusing
`band_show_index` so it can't disagree with the indices `compute_survival`
used) — years only, no dates, per requirement 7.
**Verified.** 20 unit tests in `tests/test_analysis_io.py`: the three
`fetch_*` functions and `ensure_tables` against a mocked connection (same
style as `tests/test_ops.py`); `compute_marts_from_data` covered directly
(no DB) for: correct shape and window-50 values, debut/last year computed
from real dates rather than the index (crosses a year boundary at week 55);
album grouping produces `all` + the real album + `non-album` for a
recording-only dated song; a band with no eligible songs produces nothing
for any of the three marts; two bands stay separate; `write_survival_marts`
deletes-inserts-commits on success, rolls back and re-raises on failure
(`execute_values` is a real psycopg2 function that chokes on a bare
`MagicMock` cursor — mocked it directly in these two tests rather than
fighting that), and skips INSERT entirely when there is nothing to insert.
**Mutations:** 4 tried, 1 initially uncaught — changing `SONG_MART_WINDOW`
from 50 to 25 passed every test, because my scenarios happened to give the
same outcome at both windows. Added
`test_song_mart_uses_window_50_specifically_not_some_other_window` (a
40-show history where window 25 is a clean abandonment and window 50 is
censored — window 50 doesn't even have 50 remaining shows to check); the
mutation now fails it. The other three (debut/last year swapped, the
rollback removed, and skipping the "no outcomes" `continue`) were each
caught immediately. All restored, `io.py` `diff` clean.
**arm64 check for T11 (done ahead of schedule, per your request):**
downloaded (not installed) the exact wheels `pip` would resolve for
`cp312`/`manylinux2014_aarch64` (and the newer `manylinux_2_17`/`_2_24`/
`_2_26`/`_2_27`/`_2_28` variants pip actually offers) for every package
`lifelines` pulls in that isn't already part of the base image:
`lifelines`, `autograd`, `autograd-gamma`, `formulaic`, `interface-meta`
(all pure-Python `py3-none-any` wheels — architecture is irrelevant) and
the compiled ones matplotlib needs — `matplotlib`, `pillow`, `contourpy`,
`fonttools`, `kiwisolver` (`cycler`, `pyparsing`, `python-dateutil`, `six`
are pure Python too) — every one of them has a real `cp312`-`aarch64`
manylinux wheel. Also re-confirmed the exact pinned `numpy==2.5.3`,
`scipy==1.18.1`, `pandas==3.0.5` (from the Airflow 3.3.2 constraints file)
each have one too. **No source build risk on the aarch64 VM; `lifelines`
does not need to be replaced with the hand-written estimator.** T11 can
proceed as planned: add it to `airflow/requirements.txt` (and the root
`requirements.txt` for the notebook), rebuild `encore-airflow:spec-03`, and
this check becomes moot once the real build succeeds on the branch image.
**Still not wired to real data end to end**, and not yet dbt-documented or
tested (T9), not yet called from the DAG (T10).

### T8 addendum — verified for real against the isolated database

Not only unit-tested: ran `write_survival_marts` for real against
`spec03-postgres`'s synthetic data (in a throwaway container with
`lifelines` installed on top of `encore-airflow:3.3.2`, so as not to touch
any real image ahead of T11) — 127 song rows, 464 curve rows, 123 summary
rows, no errors. `tests/spec03/test_survival_marts.py` (new, 4 tests)
compares the written marts against `oracle.survival_outcomes` (T1's
independent implementation, predating T6): for every band and the N=50
mart, the set of songs is exactly the oracle's eligible set (no more, no
less), and performances/duration/event/returned agree exactly; the
summary mart's songs/events/censored agree with the oracle at every window
(25/50/100), not only 50; debut_year/last_year fall inside the band's real
show-history year range; every real curve point is bounded and each curve
is non-increasing (the unit tests in test_survival_km.py checked the same
properties on tiny hand-built data — this repeats it at real synthetic
scale, ~127 songs across 5 bands). Manually cross-checked Muse's 7 rows by
hand first (matching them to `muse_plan()`'s roles by their performance-count
fingerprint, since real catalog song titles replace the plan's descriptive
names) before writing the automated version — all 7 matched T1's
`MUSE_EXPECTED[50]` table exactly, including which 2 of the 9 planned roles
are correctly absent (too few performances; recording-only with no year).
**A footgun found while doing this, not a pipeline bug.** Running
`dbt run --select int_show_song_sets` alone (to refresh just that view for
a quick check) made `intermediate.int_show_pairs` **disappear** — a later
test failed with `relation "intermediate.int_show_pairs" does not exist`.
Cause: dbt-postgres's view materialization does `DROP ... CASCADE` before
`CREATE VIEW`, so rebuilding an upstream view cascades away any dependent
view not included in the same `--select`. **Not a risk in the real
pipeline**: `transform`'s `dbt run` always runs the whole project, no
`--select`, so every run rebuilds every view together in one pass and
nothing is ever missing in between. It only bit me here because I was
narrowly re-selecting one view for a quick manual check. Fixed with a full
`dbt run` (127 pass + 6 warn — the same by-design NULL-year warnings as
`master`); noting it so a future narrow `--select` during spec-03
development includes `+` (downstream) or is followed by a full `dbt run`
before trusting anything built on top of the changed view.
Full suite after this: 148 passed, 14 skipped (all `tests/spec03`, opt-in).

### T9 — dbt sources, tests, forbidden columns for the survival marts (done)

`dbt/models/analytics/_survival_sources.yml`: documents
`mart_song_survival`/`mart_survival_curves`/`mart_survival_summary` as a dbt
**source** (`encore_survival`), not a model — they are written directly by
`encore.analysis.io` (D4), dbt only documents and tests them. Every column's
generic tests (`not_null`, `accepted_values` on `n_window` in {25,50,100})
are tagged `survival` at the table level, so `transform`'s own `dbt test`
(which will run `--exclude tag:survival`, see T10) never touches tables the
Python module hasn't written yet on a fresh run. New singular tests, all
tagged `survival`: `assert_survival_probability_between_0_and_1`,
`assert_survival_curve_non_increasing` (via `lag()` per band/album/n_window),
`assert_survival_summary_events_plus_censored_equals_songs` (all three from
requirement 11's own wording), `assert_survival_curve_ci_brackets_probability`
(extra, not in the spec's wording — a confidence interval that doesn't
bracket its own point estimate, or leaves [0,1], is a bug), and
`assert_song_survival_reconciles_with_int_performances` (**requirement
15**: re-derives eligibility in SQL from `int_performances` +
`int_song_catalog`, independently of `encore.analysis.survival.is_eligible`,
and compares per-band song counts against the mart). Forbidden-columns list
(`assert_no_forbidden_columns_in_analytics`) extended with `show_key`,
`show_id`, `show_index`, `setlist_url` (defensive; nothing currently uses
them). Fixed a real contradiction in `analytics/schema.yml`'s header: it
said nothing in `analytics` may carry a "song title", which `mart_song_survival.song_title`
(a legitimate MusicBrainz display title, not a raw setlist.fm one) would
have violated literally — reworded to name the four forbidden columns
specifically.
**Performance, found and fixed before it became a problem.**
`fetch_performance_counts` (T8) and the new reconciliation test both filtered
`int_performances` — a view — directly, the exact anti-pattern that made
`int_show_song_sets` take 4+ minutes at production scale in T2. The
reconciliation test took **35 s even at synthetic scale (542 setlists)**,
which was the tell; fixed both with the same `MATERIALIZED` CTE trick (query
the view once, filter afterward): the test dropped to **1.8 s**, and a full
`write_survival_marts()` run at production scale (~7,000 setlists, the same
`scripts/spec03/scale_data.sql` dataset as T2/T3) completed in **11.2 s**
total (fetch + compute + write), with all 34 `tag:survival` tests passing in
11.1 s at that size.
**An operational lesson from testing at scale, not a code bug:** while a
manual `write_survival_marts()` check was running slow (pre-fix) inside a
throwaway container, I `docker stop`'d the container to investigate — but
the query kept running server-side, and its long-held read snapshot then
blocked a later `dbt run`'s `DROP ... CASCADE` on `int_performances` with a
relation lock, hanging that dbt run for 5+ minutes. Found via
`pg_stat_activity` (a `wait_event_type = Lock` row waiting on the orphaned
query's PID) and resolved with `pg_terminate_backend()`. Recorded because it
is a real trap in this exact workflow (throwaway containers + shared
Postgres + manual `docker stop`): stopping a container is not enough to
cancel a query it started; the backend must be terminated at the database
too, or the query itself cancelled first.
**Verified.** Full project: `dbt run` 19/19, `dbt test` 160 pass + 6 warn
(the same pre-existing NULL-year warnings), 0 errors — includes the 34
`tag:survival` tests. `--exclude tag:survival` runs exactly the 133 tests
`transform` will run (unaffected by the survival marts' existence);
`--select tag:survival` runs exactly the 34 new/extended ones. **6
mutations, all caught, each on real mart data (these tables are Python-
written, not dbt models, so the mutation is a direct `UPDATE`/`DELETE`/
`ALTER TABLE`, not editing a `.sql` file) — each restored by recomputing the
marts from the source data afterward:** a probability set to 1.5; a
confidence interval's lower bound pushed above the point estimate (my first
attempt targeted `t_shows=0`, where probability is always exactly 1.0 by
construction — no row matched; redone against a real interior point);
`events` bumped by 1 so `events + censored ≠ songs`; a curve point raised
above its predecessor to break monotonicity (my first attempt raised the
wrong point, one that was already below its own successor — redone by
raising the LATER point instead); a song deleted from `mart_song_survival`
(the reconciliation test); a `venue` column added directly to
`mart_song_survival` with `ALTER TABLE` (the forbidden-columns test, dropped
again afterward). Python suite: 148 passed, 14 skipped (T8's tests, opt-in).
`tests/spec03` (real DB, opt-in): 14 passed.

### T10 — `analyze` task and runner (done)

`src/encore/dbt_runner.py`: `TRANSFORM_STEPS`'s test step now excludes the
survival tag (`("test", "--exclude", "tag:survival")` — decision D1: those
tests need marts `analyze` hasn't written yet when `transform` runs).
`SURVIVAL_TEST_SELECTOR = ("test", "--select", "tag:survival")`. New
`run_analyze()`: opens a connection, calls
`encore.analysis.io.write_survival_marts`, closes the connection in a
`finally` (even on failure), then runs the survival-tagged dbt tests against
what was just written. `airflow/dags/encore_pipeline.py`: new `analyze` task
between `transform` and `cleanup_raw_setlistfm`; unlike `transform` (which
only ever raises `DbtError`, since it's pure dbt subprocess calls),
`analyze`'s own Python code (DB I/O, the survival core) can raise other
exceptions too, so it catches `Exception` broadly rather than just
`DbtError` — documented as a deliberate difference from `transform`'s
pattern. `cleanup_raw_setlistfm` and `log_run` now also depend on
`analyzed`, not just `transformed`: without that, cleanup could start
truncating `raw_setlistfm` while `analyze` is still reading views over it —
a race, not just a missing dependency. `log_run` takes `analyzed` and
requires it to be `True` for the run to count as `success`.
**Verified.** DAG imports cleanly inside `encore-airflow:3.3.2` **without
lifelines installed** (the import chain into `encore.analysis.survival`,
where `lifelines` is imported, is lazy — inside `run_analyze()`'s function
body — so parsing the DAG never needs it; only actually *running* `analyze`
does, and that's T11's job). `scripts/spec03/check_dag_structure.py` (new):
loads the real DAG object inside the image and asserts on it directly —
task ids, that `analyze` sits exactly between `transform` and
`cleanup_raw_setlistfm`, that `cleanup_raw_setlistfm`'s and `log_run`'s
upstream sets both include `analyze`, and the trigger rules
(`cleanup_raw_setlistfm`/`log_run` = `ALL_DONE`, `analyze` = the default
`ALL_SUCCESS`). All checks passed. 22 new/changed unit tests in
`tests/test_dbt_runner.py` for `run_analyze` (writes then tests, in order;
closes the connection even when the write raises; propagates a failing
survival test) plus the existing `run_transform` tests updated for the new
test-step tuple; 2 mutations tried (dropping the `finally` around
`conn.close()`, swapping the survival selector from `--select` to
`--exclude`), both caught. Full suite: 151 passed, 14 skipped (T8/T9's
DB-level tests, opt-in).
**Deliberately not done, and not attempted:** a real, scheduled
`airflow dags test`/`airflow tasks test` run of the modified DAG (proving
"analyze fails → cleanup still runs" by actually triggering it) needs an
Airflow metadata database, and the only one available is the MAIN stack's,
which is off limits for spec-03 work (it is pointed at the `master`
checkout's DAG folder, not this branch's). Spinning up a second, fully
isolated Airflow scheduler + metadata DB against `spec03-postgres` just for
this one check would be a disproportionate amount of new infrastructure for
what it proves: the mechanism itself (`trigger_rule=ALL_DONE` on a
downstream task, unchanged from `transformed`) was already proven for real
via actual DAG runs in spec-02a (item 20, and the acceptance runs), and
`analyzed` is wired into `cleanup_raw_setlistfm`'s upstream set in exactly
that same, already-proven way — the structural check above confirms the
wiring is actually present, not just intended. **This is the one thing T14
must still confirm for real**: after the merge, a full pipeline run on
`master` should be watched to see `analyze` actually execute in its correct
position and `cleanup_raw_setlistfm` still run if it were to fail (not
expected to fail on real data, but worth watching once).

### T11 — image with lifelines (done 2026-09-23)

- `lifelines` added to `airflow/requirements.txt` (unpinned, the Airflow
  constraints file decides) and to root `requirements.txt` (`==0.30.0`): the
  notebook does not need it, but the host unit tests (`tests/test_survival*.py`)
  import it, so the dev environment does.
- Built `encore-airflow:spec-03` (id `9dd295366879`, 3.81 GB; +~140 MB over the
  main image) with `DBT_GIT_COMMIT=spec-03-<hash>`. Never tagged `:3.3.2`, no
  `docker compose`: `encore-airflow:3.3.2` still `327c94e2db5d`, main
  containers untouched.
- Resolved: lifelines 0.30.0, numpy 2.5.3, scipy 1.18.1, pandas 3.0.5,
  matplotlib 3.11.2 (numpy/scipy/pandas come from the base image). No source
  build except `autograd-gamma` 0.5.0, a pure-Python sdist (no compiled files).
- **arm64:** `pip download --platform manylinux2014_aarch64/manylinux_2_28_aarch64
  --only-binary=:all: --python-version 3.12` succeeded for all 10 new packages
  (autograd, contourpy, cycler, fonttools, formulaic, interface-meta,
  kiwisolver, lifelines, matplotlib, pillow).
- In the built image (no `pip install` step): `write_survival_marts` gives
  127 / 464 / 123 rows (same as the throwaway-container run in T8), and
  `tests/spec03` + `tests/test_survival.py` + `tests/test_survival_km.py` pass
  (41 passed; pytest installed in a throwaway container only).
- `scripts/spec03/env.sh`: `S3_IMAGE` now defaults to `encore-airflow:spec-03`.
- Environment note: the host `.venv` can no longer import scipy (a Windows
  Application Control policy blocks its DLL), so lifelines-dependent tests run
  in the branch image, not on the host.

### T12 — notebook (done 2026-09-23)

`notebooks/02_rotation_survival.ipynb`, same pattern as notebook 01: a
`read_analytics()` allow-list of the three marts, read-only session, DB from
env vars (`ENCORE_DB_HOST` / `ENCORE_DB_PORT`, default 127.0.0.1:5435). Three
pieces: (1) rotation by year, small multiples, one panel per band, shared 0-1
y axis, years with < 5 pairs drawn hollow and left out of the line; (2)
Kaplan-Meier curves for one band (`BAND`), one step line per album with a
shaded 95% band, `non-album` grey, dashed "all eligible songs" line, only
albums with >= 5 songs; (3) median survival table for N = 50 (`not reached`
when the curve never crosses 0.5, `*` on albums with < 5 songs).
Verified by executing a copy (in the scratchpad, never in the repo) against
`spec03-postgres` with `ENCORE_DB_PORT=5446`: no errors, both figures and the
table rendered and were inspected. The synthetic data is thin (one year for
one band, no abandonment events), so the curves are flat at 1.0 there; the
layout, not the numbers, is what this preview validates. The committed file has
0 outputs and 0 execution counts. The optional executed HTML in `reports/` was
skipped (it would only show synthetic data); generate it after the real run.

### T14 — merge, full run, acceptance (done 2026-09-23)

- **Budget before the run:** 0 setlist.fm requests logged for 2026-09-23 (UTC),
  estimate 481, DAG ceiling 1300. Run used **479** requests, 0 MusicBrainz
  (cached).
- **Merge:** `master` was an ancestor of `spec-03`, so a fast-forward (no
  merge commit). Main image rebuilt as `encore-airflow:3.3.2` (id
  `fd2272134af9`, dbt project commit `5920122`), containers recreated, DAG
  imported cleanly, `lifelines` 0.30.0 present. DAG paused again after the run.
- **Run** `manual__2026-09-23T15:17:26`: all tasks success in order
  (transform 15:29-15:32, analyze 15:32:23-15:32:43, cleanup, log_run);
  `ops.pipeline_runs` status `success`; `raw_setlistfm` empty (0 setlists) after
  the run. Per band setlists: Muse 1722, Oasis 958, Metallica 2192, Linkin Park
  1042, Arctic Monkeys 1095, Avenged Sevenfold 1408, Twenty One Pilots 1083.
- **Tests:** transform `dbt test` PASS=131 WARN=2 ERROR=0, including
  `assert_marts_reconcile_with_int_performances` PASS; the 2 warns are the
  known 457 recordings without a release year. analyze wrote 664 song / 3548
  curve / 219 summary rows and `dbt test --select tag:survival` PASS=34, including
  `assert_song_survival_reconciles_with_int_performances` PASS.
- **Sanity 1 (Metallica rotation above Muse in recent tours): OK.** Metallica
  M72 World Tour (2023-2026) 0.750; Muse recent tours 0.132-0.287. By year
  (2023): Metallica 0.871, Muse 0.177.
- **Sanity 2 (debut-album songs still played are censored with very long
  durations): DEVIATES, explained.** Durations are long (debut-album median
  161-334 shows for Metallica, Oasis, Muse, Linkin Park, Arctic Monkeys), but
  most songs still played today are abandonment events, not censored, because
  only the *first* 50-show gap counts (decision Q2) and they returned after it
  (`returned_after_abandonment`). Genuinely censored songs do have very long
  durations (Metallica 19 censored, mean 830 shows). Avenged Sevenfold and
  Twenty One Pilots have short debut-album durations (mean 57 and 45): early,
  little-played albums. Documented in `docs/methodology.md`; changing the rule
  (for example counting the *last* gap, or treating returns as censoring) is a
  decision for the owner, not made here.
- **Sanity 3 (N = 25/50/100 differ but not drastically):** mostly yes (medians
  for `all`, e.g. Metallica 121/152/196, Muse 133/172/192, Oasis 105/115/122);
  larger jumps for Avenged Sevenfold (81/87/174) and Twenty One Pilots
  (102/150/245).
- **analyze failure path — SIMULATED, not real.** The real run succeeded, so
  the failure path was checked in isolation instead: the real `encore_pipeline`
  DAG object run in-process with `dag.test()` in a throwaway container (private
  sqlite Airflow metadata, `spec03-postgres`, external I/O stubbed, `run_analyze`
  made to raise). Result: `analyze` failed, `cleanup_raw_setlistfm` ran
  (`truncate_all` called at start and at cleanup) and `log_run` ran and wrote
  `status = failed`; the control run without injection wrote `success`. Note the
  DagRun itself reports `success` because its leaf task `log_run`
  (`all_done`) succeeds, the same as for a `transform` failure since spec-02a:
  read `ops.pipeline_runs.status`, not the DagRun state. Script:
  `failure_path.py` was kept in the session scratchpad only.
- **Numbers per band** (N = 50, catalog songs, `album = all`): songs /
  abandoned / censored / median shows: Arctic Monkeys 90/70/20/152, Avenged
  Sevenfold 71/54/17/87, Linkin Park 98/70/28/141, Metallica 107/88/19/152, Muse
  125/99/26/172, Oasis 80/72/8/115, Twenty One Pilots 93/62/31/150. Rotation
  (mean Jaccard rotation weighted by pairs, all years): Arctic Monkeys 0.149,
  Avenged Sevenfold 0.241, Linkin Park 0.174, Metallica 0.239, Muse 0.239, Oasis
  0.098, Twenty One Pilots 0.209; 165 scored tours, all in [0, 1].

### T14 addendum — abandonment rule changed to the last gap (2026-09-23)

**Why.** Sanity check 2 of the first real run (debut-album songs still played
today should be censored) failed for a real reason: only the first 50-show gap
counted, so songs dropped for a tour and brought back were events. Decision by
the owner: the event is the LAST gap.

**New rule** (`docs/methodology.md`, spec section Part B, `product.md`): a gap is
N or more consecutive shows without the song, inside the history. A song is
abandoned only if its FINAL gap (after its last appearance) is a full gap, i.e.
it left and did not return. Otherwise it is censored (still played, or it
returned). **Duration is one rule for every song** (owner decision, same day):
debut to the song's last appearance, inclusive, never extended to the end of the
history.
`returned_after_abandonment` = at least one intermediate gap;
new column `gaps_count` = number of intermediate gaps (mart_song_survival, N=50).

**Code and tests.** `src/encore/analysis/survival.py` (`WindowOutcome`,
`outcome_for_window`, `SongSurvival.gaps_count`), `io.py` (column plus an
`ALTER TABLE ... ADD COLUMN IF NOT EXISTS gaps_count` so the existing production
table migrates on the next run), dbt source docs and a new singular test
`assert_song_survival_gaps_consistent`. Independent oracle rewritten from the
literal definition; synthetic Muse plan gained a `returns_and_stays` song (two
intermediate gaps, still played at the end). Unit tests cover a song that returns
and stays, a song that returns and then leaves for good, gap boundaries, and the
end-to-end scenario. Five mutations (final-gap `>=`, a returned song counted as
an event, intermediate-gap boundary, censored-returned duration, censored duration
extended to the end of history) each turn a test
red; the dbt consistency test was also turned red by hand and restored.
Full suite in the branch image against `spec03-postgres`, DB-level tests on:
170 passed; `dbt test --select tag:survival` PASS=36. The isolated table was
created with the old shape first, so the `ALTER` migration ran for real there.

**Not done: the real marts still hold the OLD first-gap numbers.** `analyze`
reads the views over `raw_setlistfm`, which is empty after every run, so it
cannot be re-run alone: a full pipeline run (~480 setlist.fm requests) on the new
code is needed, after `master` gets this commit and the main image is rebuilt.
The T14 sanity-check numbers above (event counts, debut-album section) describe
the old rule and must be re-read after that run.

**The T14 caveat "read returned_after_abandonment together with the curves"
no longer applies.**

## 11. Handoff for the next session (2026-09-23)

T0-T13 done and pushed to `origin/spec-03` (last commit: see
`git log -1`). T14 stays blocked until the user says
to do it.

**T13 done (2026-09-23, commit `5920122`):** `docs/methodology.md`
(rotation/core-song definitions, the full duration/abandonment/censoring
convention, the Q4/Q5 jam and recording-only-without-year caveats),
`dbt/README.md` (new "Running the `analyze` task" section, `tag:survival`
split explained next to how `transform` is documented), root `README.md`
(architecture diagram and prose now show `analyze` between `transform` and
`cleanup_raw_setlistfm`), `docs/context/structure.md` (`src/encore/analysis/`
added to the layout). Docs only, no code touched; fast unit test suite
(151 passed, 14 skipped) re-run as a sanity check, not because docs could
break it.

### Where things are right now

- Main stack (`master`, `D:\projetos\encore`): untouched, image
  `encore-airflow:3.3.2` id `327c94e2db5d`, containers healthy, branch
  `master`, clean tree. Nothing in this session touched it.
- Worktree: `D:\projetos\encore-spec03`, branch `spec-03`, clean tree, pushed.
- Isolated environment: container `spec03-postgres` (network `spec03-net`),
  synthetic data loaded (542 setlists, `tests/support/histories.py`'s
  scenarios). Bring it back with `bash scripts/spec03/up.sh` if the
  container was stopped between sessions (data survives in the volume).
- `lifelines` is installed **only** in the shared host dev `.venv`
  (`D:\projetos\encore\.venv`, shared by both worktrees) — not in any
  `requirements.txt`, not in any image. Every real-data check so far
  (T7-T10) used a **throwaway container** that `pip install`s it on top of
  `encore-airflow:3.3.2` each time (see the `docker run ... pip install -q
  lifelines ...` pattern used throughout `docs/specs/spec-03-progress.md`'s
  T8/T9 log entries) — nothing durable exists yet. T11 is exactly "make this
  durable": add it to the real requirements files and build the real branch
  image.
- arm64 wheels for `lifelines` and everything it pulls in (including the
  compiled ones matplotlib needs, and the exact pinned numpy/scipy/pandas
  versions) were confirmed present in T8's log entry — no source-build risk
  found. T11 should not need to re-derive this, just act on it.

### T11 — image with lifelines (not started)

Plan (from section 5's task table): add `lifelines` to
`airflow/requirements.txt` and to the root `requirements.txt` (the notebook
in T12 will need it too, to read `mart_survival_curves` and maybe refit nothing
— actually the notebook only reads the marts, it does not need lifelines
itself; double check whether the root `requirements.txt` really needs it
before adding it there, or whether only `airflow/requirements.txt` does).
Then:

    export DBT_GIT_COMMIT="spec-03-$(git -C /d/projetos/encore-spec03 log -1 --format=%h)"
    cd /d/projetos/encore-spec03
    docker build -t encore-airflow:spec-03 -f airflow/Dockerfile .   # NOT docker compose, NOT the :3.3.2 tag
    # verify the pinned versions actually resolved (no source build happened):
    docker run --rm --entrypoint python encore-airflow:spec-03 -c "import lifelines, numpy, scipy, pandas; print(lifelines.__version__, numpy.__version__, scipy.__version__, pandas.__version__)"

Then re-run `write_survival_marts` (T8/T9's throwaway-container command,
without the `pip install` step this time — the image already has it) and
the full `tests/spec03` suite, to confirm the durable image behaves
identically to the throwaway one. Update
`scripts/spec03/env.sh`'s `S3_IMAGE` default to `encore-airflow:spec-03`
once it exists, so later `s3py`/`s3dbt` calls use the real branch image
instead of falling back to `encore-airflow:3.3.2` (which doesn't have
lifelines and would make `s3py` calls that import
`encore.analysis.survival` fail).
**Never** build with tag `encore-airflow:3.3.2` or run `docker compose`
from this worktree — that would overwrite the main stack's image (see D3 /
the T0 guardrails).

### T12 — notebook (not started)

`notebooks/02_rotation_survival.ipynb`, reading only from `analytics`
(same pattern as `notebooks/01_first_kpi.ipynb` on `master`: a
`read_analytics()` allow-list, read-only session, `DB` config from env vars
so it can point at `encore_spec03`/`spec03-postgres` for a dev preview and
at the real database once merged). Three pieces, per the spec:
1. Rotation by year, small multiples, one panel per band, same y scale
   (from `mart_band_rotation_by_year`).
2. Kaplan-Meier curves for one band, one line per album, with confidence
   bands (from `mart_survival_curves`; Q6's default — only draw albums with
   >= 5 songs, from `mart_survival_summary.songs` — still applies here).
3. Table of median survival by band and album for N = 50 (from
   `mart_survival_summary` filtered to `n_window = 50`).
Outputs cleared before committing (0 outputs, 0 execution counts, checked
the same way item 21/notebook 01 was). An executed HTML MAY go to
`reports/` (gitignored) as with notebook 01 — optional per the spec text
("may be generated"), do it if there's time, skip if not.
Load the `dataviz` skill again before writing chart code (small multiples
need consistent axes across panels; confidence bands are a new chart type
this project hasn't drawn before — check `references/marks-and-anatomy.md`
for how to draw a band, not just a line).

### T13 — documentation (not started)

Per section 5's task table: `docs/methodology.md` (rotation and core-song
definitions, the abandonment/censoring convention exactly as decided in
section 4a — duration inclusive, N=25/50/100, eligibility rule — and the
Q4/Q5 caveat about jams/generic titles and about recording-only songs
without a release year being ineligible), `dbt/README.md` (document the
`analyze` task and the `tag:survival` split, matching how the existing
"Running dbt inside Airflow" section documents `transform`), root `README.md`
(update the architecture diagram/description to mention `analyze` and the
survival marts, matching how it already documents `transform`), and
`docs/context/structure.md` (add `src/encore/analysis/` to the layout).
None of this touches `master` until T14.

### One open thread, not urgent

`docs/specs/spec-02a-followup-progress.md`'s "Bug found and fixed" entry
about `check_api_budget` comparing against a manually-supplied
`airflow dags test <date>` logical date instead of `finished_at` is still
just flagged, not fixed, on `master`. It is unrelated to spec-03 and does
not block anything here; mentioned so it isn't forgotten if a future
session is picking priorities.
