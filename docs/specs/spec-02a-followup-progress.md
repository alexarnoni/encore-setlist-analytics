# Spec 02a — Follow-up after acceptance

Work requested by the project owner when accepting spec 02a
(`docs/specs/spec-02a-progress.md`, now closed). Same discipline: one
commit per item, results recorded here.

## Checklist

- [x] **1. Close `spec-02a-progress.md`** and record both decisions —
      status banner added, acceptance and the two decisions logged.
- [x] **2. `docs/context/product.md`** — four bullets under *Key metric
      rules*: `match_rate_by_album` secondary/informational; "non-album"
      category for era KPIs; first-official-release-year rule (reference
      album stays the basis for eras); warn-level check for recording
      dates more than 2 years before the album year.
- [x] **3. Release year = first official release year** in
      `int_song_catalog`, plus a warn-level audit of suspicious
      recording dates and a way to fix a year through the override seed.
      `release_year = coalesce(seed fix, least(album_year, recording_year))`;
      `album_year`, `recording_year` and `release_year_fixed` are kept as
      columns; the reference album (and so era KPIs) is unchanged. The
      audit is the view `intermediate.int_song_release_date_audit` (built
      from MusicBrainz only) plus the warn-severity singular test
      `assert_song_recording_date_not_far_before_album`. **The override
      seed had no way to correct a year**, so `seed_song_overrides.csv`
      gained an optional `first_release_year` column: a row with only
      band + canonical title + year fixes that song (existing seed tests
      ignore such rows). Five new tests: release-year rule re-derived with
      explicit CASE logic, and fix validity / uniqueness / matches-catalog.
      **Found while verifying:** a plain `dbt seed` does not add a column
      to an existing seed table (it "loaded" a header-only seed and left
      the old shape, then the model failed). The `transform` task now runs
      `dbt seed --full-refresh` (unit tests updated); documented in
      `dbt/README.md`.
      **Verified for real** on the Oasis + Arctic Monkeys catalog (958
      songs): (1) independent Python recompute from `stg_album_tracks` and
      `stg_recordings` → **0 mismatches**; (2) against the pre-change
      snapshot, exactly **22 songs changed** (Oasis 8: 7 by 1 year and
      *Let There Be Love* by 4; Arctic Monkeys 14, all by 1), every change
      to an earlier year, 0 recording-only songs changed; (3) mutations:
      old rule (album year only) → the rule test fails on 733 rows; audit
      threshold `> 0` → warn goes 1 → 22, `> 4` → 0; (4) seed mechanism
      with temporary rows: a valid fix moves *Let There Be Love* to 2005,
      marks it fixed and empties the audit; a malformed year, a 1850
      year, a title typo and two conflicting years each fail exactly the
      intended test. All restored (seed header-only, `diff` clean).
      **Audit result now: 1 song flagged** — Oasis, *Let There Be Love*
      (album *Don't Believe the Truth* 2005, recording 2001). None for
      Arctic Monkeys. Coverage limit: no song has a gap of exactly 2 years,
      so `> 2` vs `>= 2` is not observable with this data.
- [x] **4. `match_rate_by_album`** in `mart_match_quality` (informational)
      — share of performances matched to a song with a reference studio
      album (`reference_album is not null`: album source, or an override
      naming an album). New column after `match_rate_by_title`; range test
      extended, internal-consistency test now also requires it not to
      exceed `match_rate_by_performance`. A new test re-derives it from
      `int_performances` with a different expression (matched and
      catalog_source not `recording`). **Verified for real:** independent
      Python recompute (album keys from `stg_album_tracks`) → 20 cells,
      **0 mismatches**; overall Oasis 10,400 / 11,969 = **0.8689**
      (matches the 0.869 measured before); the pre-existing columns are
      unchanged vs the snapshot (0 cells). Mutations: album rate counting
      every matched play → *only* the new derivation test fails (19 cells;
      the range and consistency tests pass, which is why it exists); `*2`
      → range, consistency and derivation tests all fail. Restored.
      Full `dbt test`: 87 pass + 3 warn (the audit list, plus the 2
      NULL-year warnings, now 89 rows because the catalog includes Arctic
      Monkeys); pytest 62 passed.
      (Caught and fixed on the way: my first `schema.yml` edit had dropped
      the warn-level `not_null` on `release_year`; the warn count going
      from 3 to 2 exposed it.)
- [x] **5. Notebook: legend upper left** instead of direct labels — the
      legend is now always drawn in the upper left (single band included);
      the end-of-line labels are gone.
- [x] **6. Notebook: years with fewer than 3 shows** as hollow markers,
      left out of the connecting line, rule noted under the title —
      `MIN_SHOWS = 3`; shows per band/year = sum of `shows` over the tour
      cells (a show belongs to one tour). The note sits between the title
      and the plot. Executed a scratch copy against the live marts and
      looked at the chart: Oasis years 1991, 2004 and 2007 are hollow and
      outside the line, 2025 (23 shows) is a filled isolated point, legend
      upper left. Committed `.ipynb` has 0 outputs / 0 execution counts.
      Only Oasis is loaded, so the several-band legend is still unseen.
- [x] **7. Rerun dbt on the current Oasis data** and report how
      `avg_repertoire_age` changed. `raw_setlistfm` was empty, so the
      Oasis fixture was reloaded first (958 setlists / 13,170 entries, 49
      requests, identical to before); before-values are the marts as they
      stood under the old rule (snapshot taken beforehand).
      **Result:** `performances` and `matched_performances` are identical
      in all 36 cells; `avg_repertoire_age` changed in 31 of 36.
      Overall (weighted by matched performances) **6.237 → 6.433 years
      (+0.196)**, confirming the ~0.2-year low bias flagged when the
      album-year rule was first questioned. By year the shift is +0.07 to
      +0.41 (largest: 1994 +0.41, 2007 +0.40, 2000 +0.28); 1991-93 do not
      move (age clamped at 0 / songs new at the time); 2025 goes 29.96 →
      30.13. By tour: *Definitely Maybe* 0.29 → 0.69 (+0.40), the others
      +0.10 to +0.28. `oldest_song_year` overall stays 1991. Cause: 22
      catalog songs moved to an earlier year (8 Oasis; see item 3).
- [x] **8. Full pipeline, all 7 bands** (`ENCORE_BANDS_FILTER` empty), after
      a setlist.fm request-budget check.
      **Budget check.** Phase 0 show counts (9,499) → 479 pages/requests
      expected; 241 already used that day → 720 projected, under the DAG's
      1,300 cap and the API's 1,440. MusicBrainz for the 5 missing bands
      was preloaded first with a one-off script: 0 real requests (answered
      from the Phase 0 disk cache), 64 albums = 59 after the 5 seed
      exclusions; all dbt tests then passed on 7 bands' catalogs, so a
      dbt failure could not burn the setlist.fm quota afterwards.
      **Run 1 (17:36-17:49): succeeded, but with the wrong dbt.** I had not
      rebuilt the Airflow image after items 3-4, and `transform` uses the
      copy of `dbt/` baked into the image: it ran the OLD project (80
      tests, no `match_rate_by_album`, old release-year rule). The
      symptom was in the log (80 vs 87 tests) and I missed it; the
      dbt/README already said a rebuild is needed. My error. The same run
      exposed a counting bug: `ops` logged **1,795** requests for 481 real
      ones, because `extract_setlistfm` never reset the shared request
      counters and `log_run` summed the running totals (per-band values
      49, 137, 192, 247, 318, 371, 481; 12 minutes of wall time is
      inconsistent with 1,795 calls at 1 s each). It would also have made
      the next run's budget estimate 1,795 and blocked it. Fix:
      `reset_counters()` at the start of the task (commit `9f3c254`); the
      logged row was corrected 1,795 → 481 in `ops`.
      **Run 2 (17:53-18:05): rebuilt image, correct.** 14 tasks ok, dbt
      seed 3/3, run 14/14, test **87 pass + 3 warn**, `raw_setlistfm` 0 / 0
      / 0, `ops` row `success`, 483 requests (per-band counts now sum
      correctly). Setlist.fm requests used that day: 241 + 481 + 483 =
      **1,205** (the second run was needed only because of the stale
      image). `encore_pipeline` stayed paused throughout.
- [x] **9. Report** — per-band results were delivered in chat; no band is
      below 0.90, so no unmatched-title list was needed. Numbers
      (`match_rate_by_performance` / `match_rate_by_album`): Metallica
      0.9999 / 0.9364; Oasis 0.9999 / 0.8689; Arctic Monkeys 0.9947 /
      0.9511; Twenty One Pilots 0.9906 / 0.9473; Muse 0.9897 / 0.9313;
      Avenged Sevenfold 0.9881 / 0.9572; Linkin Park 0.9750 / 0.9149
      (album rate is the performance-weighted mean of the per-year
      rounded rates). Date check: 1 song flagged over all bands (Oasis,
      *Let There Be Love*). Weak spot: Muse 1994-95 (59 performances,
      0 % and 24 % matched). 457 catalog songs have no release year
      (Metallica 232). Not verified: an independent recomputation of the
      marts for the six bands other than Oasis (raw data is deleted
      after each run); they rest on the shared, tested code.

## Log

## Round 2 — after review of the full 7-band run

Constraint for the whole round: no new pipeline run today (setlist.fm
budget nearly spent: 1,205 of 1,300 used). Because `raw_setlistfm` is
empty, `dbt run` / `dbt seed --full-refresh` are NOT run against the real
`encore` database — they would rebuild the marts from nothing and wipe the
only copy of the 7-band results. Items 1, 4 and 5 get their real-run check
on the next full run.

- [x] **R2-1. Override seed: *Let There Be Love* (Oasis) → 2005** — one row
      in `seed_song_overrides.csv` (`Oasis,,Let There Be Love,,2005`): the
      official release is *Don't Believe the Truth*; the 2001 recording is
      not an official release. Checked: CSV has 5 fields per row, the
      project parses, marts untouched (404 rows). Takes effect on the next
      run's `dbt seed`; the audit list should then be empty.
- [x] **R2-2. Muse 1994-1995 low match** recorded as an accepted known
      limitation in the new `docs/methodology.md` (linked from
      `product.md`). No data change.
- [x] **R2-3. Songs without a release year — analysis only, nothing
      changed.** *Cannot be answered from the marts as they are:* no mart
      column records how many performances entered the average, so the
      share of performances whose song has no year is not derivable. What
      the marts do give: a lower bound of 0 for every band (no cell with
      matched performances has a NULL average) and an **upper bound** —
      only recording-only songs can lack a year (all 457 catalog songs
      without a year are recording-only; album and override songs always
      have one), so the share is at most `match_rate_by_performance −
      match_rate_by_album`: Oasis 13.1 % (known to be 0 from item 12),
      Metallica 6.4 %, Linkin Park 6.0 %, Muse 5.9 %, Arctic Monkeys 4.4 %,
      Twenty One Pilots 4.3 %, Avenged Sevenfold 3.1 %. All bounds exceed
      2 %, so no band can be cleared or flagged. The top-20 affected titles
      by performance count also cannot be produced (no titles or play counts
      outside a run). Catalog side (MusicBrainz, persistent), songs without
      a year / all songs: Metallica 232/1,523 (15.2 %), Oasis 63/738,
      Muse 57/540, Linkin Park 56/1,127, Arctic Monkeys 26/220, Twenty One
      Pilots 12/453, Avenged Sevenfold 11/242.
      **Likely cause (evidence in the catalog):** all 510 MusicBrainz
      recordings behind those 457 songs have `first_release_date` NULL, and
      the titles are mostly bootleg/live-track entries: jams, solos, medleys
      written "A / B", version or venue annotations ("(live at the Forum)",
      "(Semi-Acoustic version)"), and misspellings of real songs ("Master of
      Puppet", "Ecstacy of Gold", "Fake Tales of San Fransisco"). Generic /
      instrumental-looking titles: Metallica 89 of 232, Avenged Sevenfold
      11 of 11. So the effect is real but probably concentrated in the
      bands with many live-recording entries (Metallica first). Not
      measured on performances.
      **Proposals, none applied:** (1) add `aged_performances` (performances
      with a known age) to `mart_repertoire_age` so every run reports the
      per-band share directly — the missing piece; (2) tomorrow's run
      produces the numbers, and a dev-fixture reload would be needed for
      titles; (3) fixes would be alias rows in `seed_song_overrides.csv`
      for the misspellings that are really album songs, and treating
      undated recording-only songs as a separate "matched, undated"
      category rather than as age data.
- [x] **R2-4. Reconciliation test in every run** —
      `assert_marts_reconcile_with_int_performances`: per band, performances
      and matched performances summed over each mart must equal
      `int_performances` (bands taken as the union of the three, so a
      missing or extra band fails). **Deviation, flagged:** compared with
      the rows that have a known `show_year`, not every row, because both
      marts exclude undated performances by design and a strict all-rows
      equality would fail on any band with an undated setlist; a companion
      warn test `assert_no_undated_performances_left_out_of_marts` reports
      how many are excluded per band. Runs in `transform`'s `dbt test`, so a
      mismatch fails the run.
      **Verified in a scratch database** (`encore_scratch`: MusicBrainz
      copied from the real DB, 4 synthetic setlists for Oasis and Muse incl.
      a cover, a tape entry, an unmatched song and an undated show; the
      real database was not touched, marts still 404 / 172 rows): green on a
      correct build (6 dated Oasis / 4 Muse performances, matched 5 / 3);
      four mutations each fail it with the expected columns diverging —
      age mart +1 performance; quality mart dropping unmatched rows (only
      the quality columns differ); a whole band missing from the age mart
      (1 row); age mart matched = all (only the age matched column
      differs). **A slip worth recording:** my first mutation pass restored
      files but did not rebuild the marts between mutations, so results
      after the first were contaminated by leftovers (a "2 rows" where 1
      was expected exposed it); M2-M4 were redone with a clean rebuild
      before each. The same scratch run also confirmed R2-1: with the seed
      row, *Let There Be Love* gets 2005, `release_year_fixed` true, and the
      audit list is empty. Limit: the test guards mart drift against
      `int_performances`; an error inside `int_performances` itself (both
      marts inherit it) is not caught by it. On the real DB today the test
      is red for all 7 bands, by design (raw is empty, marts are full);
      documented in `dbt/README.md`.
- [x] **R2-5. Dev volume for `./dbt` + dbt project version in the log.**
      *Volume:* new `infra/docker-compose.dev.yml` (layered on the base file
      by `make up-dev`) bind-mounts `./dbt` **read-only** over
      `/opt/airflow/dbt` in the four Airflow services; the base file and the
      Dockerfile `COPY` are unchanged, so production (`make up`) still runs
      the image's copy. dbt writes only to `/tmp`, hence `:ro`. *Version
      log:* `run_transform()` now logs, before any dbt step,
      `dbt project: commit=<hash> content_sha=<hash> dir=...`. The commit
      cannot come from git inside the image (`.git` is not copied), so the
      Dockerfile takes `ARG DBT_GIT_COMMIT` -> `ENV ENCORE_DBT_COMMIT`
      (the Makefile exports it as the last commit touching `dbt/`, plus
      `-dirty` if `dbt/` has uncommitted changes; `make build` bakes it), and
      `dbt_project_commit()` falls back to `git log` in a checkout, then to
      `unknown`. I added a `content_sha` (hash of the project files, ignoring
      `target/`, `logs/`, `.user.yml`) that was not asked for: with the mount
      the commit is fixed at `up` time while files keep changing, so only the
      content hash tells the truth. Also new: `make up-dev`, `make build`;
      README and `dbt/README.md` updated (including the stale-image warning).
      **Verified for real** (not via a pipeline run, which is barred today):
      merged compose config shows the `:ro` mount and `ENCORE_DBT_COMMIT` for
      the dev file and no dbt mount for the base file; image built with
      commit `41527b1` and stack restarted with the dev file (DAG still
      paused); inside the scheduler container the mount is `rw=false`, sees
      29/29 test files, shows a probe file created on the host at once, and
      refuses a write ("Read-only file system"); the real `run_transform()`
      with dbt replaced by `/bin/echo` (so no database access) logs
      `dbt project: commit=41527b1 content_sha=abc1257f845b` first, then the
      three steps; the image alone, without the mount, logs the same commit
      and the same `content_sha` (dev mount and image agree when in sync);
      an uncommitted host file changes the content hash in the running
      container (`abc1257f845b` -> `28946ee57564` -> back). Unit tests: 8 new
      (fingerprint stability/ignored paths/missing dir, baked commit, git
      fallback with a real temp repo, no-git, log fields, order in
      `run_transform`); 4 mutations each caught. pytest 70 passed. Not
      verified: `make` itself (not installed in this shell; its `DBT_GIT_COMMIT`
      expression was run by hand) and the log line inside a real pipeline
      run (tomorrow).
- [x] **R2-6. Executed notebook as HTML, all 7 bands** —
      `reports/01_first_kpi.html` (new gitignored folder `reports/`, checked
      with `git check-ignore`; generated with `nbconvert --execute` from a
      copy so the committed notebook keeps 0 outputs). Executed against the
      live marts (404 + 172 rows, 7 bands). Looked at both charts: the
      7-line chart has the legend upper left without covering data, one
      fixed colour per band, hollow markers for years with fewer than 3
      shows. Yearly peak of the average age per band, from the marts:
      Metallica 32.3 (2022; 25-32 in 2020-26), Oasis 30.1 (2025), Linkin
      Park 15.7, Muse 14.6, Avenged Sevenfold 12.8, Arctic Monkeys 10.8,
      Twenty One Pilots 7.8). The file contains no password, API key
      or forbidden column names. Note: the marts still reflect the run-2
      data, i.e. *Let There Be Love* at 2001 until the next run applies the
      seed fix. The scratch database used in R2-4 was dropped afterwards.
      Final state: image rebuilt at HEAD (commit `90fc50b`), stack running
      with the dev mount, mounted and baked copies report the same
      `content_sha` (`80f491fe03c2`), DAG paused, `raw_setlistfm` empty,
      marts intact.

### Left for tomorrow's full run (no pipeline run was made today)

- R2-1: the seed row should give *Let There Be Love* 2005, mark it fixed and
  leave the audit list (and its warn test) empty.
- R2-4: `assert_marts_reconcile_with_int_performances` must be green with the
  real 7-band data; the warn companion reports any undated performances.
  If red, the first suspect is undated setlists or a mart filter, not the
  data.
- R2-5: the first log line of the transform task must read
  `dbt project: commit=... content_sha=...`.


## Round 3 — preparing tomorrow's run to answer "songs without a release year"

Requested after the round-2 review (items 1, 2, 4, 5 and 6 accepted, including
the reconciliation deviation). Still no pipeline run today; validation is done
on a scratch database (`encore_scratch`: MusicBrainz copied from the real DB,
7 synthetic setlists for Oasis / Metallica / Muse, dropped afterwards) and the
real `encore` database was not touched (marts 404 / 172, raw empty).

- [x] **R3-1. `aged_performances` in `mart_repertoire_age`** — matched
      performances whose song has a release year, i.e. those that entered the
      average (`count(*) filter (where is_matched and age is not null)`);
      `matched_performances - aged_performances` is the matched-but-undated
      part. Schema entry (`not_null`), new singular test
      `assert_mart_repertoire_age_internal_consistency` (aged <= matched <=
      performances; average/median/oldest/newest NULL exactly when aged = 0),
      and `assert_marts_reconcile_with_int_performances` now also reconciles
      `aged_performances` with `int_performances`. **A gap found while
      mutation-testing:** the consistency test alone cannot catch aged counting
      every matched performance (aged <= matched still holds), so the
      reconciliation had to be extended. Scratch results: correct build green;
      aged = all matched -> *only* the reconciliation fails (Metallica 2 vs 6,
      Oasis 3 vs 4); aged = all performances -> both fail; aged = 0 -> both
      fail. Hand-checked values: the Oasis 2005 cell has 3 performances, 2
      matched, 1 aged (average 10.0 from *Wonderwall* alone).
- [x] **R3-2. Diagnostic lists in the task log** —
      `src/encore/transform_report.py`, called by `run_transform()` after
      `dbt test`. Per band: a summary line (performances, matched, matched
      with / without a release year, unmatched, with shares), the top 20
      catalog songs **without a release year** (count and `catalog_source`),
      and the top 20 **unmatched** setlist titles (count). A query inside the
      task rather than a dbt operation (formatting and unit tests are easier in
      Python). Read-only session, no temp tables, output through `logging`
      only, titles collapsed to one line and capped at 80 characters (they are
      setlist.fm text going into a log). It never raises: a failure is a
      warning. **Design choice, flagged:** it runs after `dbt test` even when a
      test fails (raw data is deleted right after, and a failing run is when
      the titles help most; it also stops a red reconciliation test from
      wasting the day's quota), and it does not run if `seed` or `run` failed.
      Scope = performances with a known show year, like the marts.
      **Verified:** 13 unit tests (formatting, read-only queries, session
      flags, never raising, `top_n` passed through, ordering relative to the
      dbt steps, skipped when seed/run fail, still runs and re-raises when the
      test fails); mutations (no `finally`, report also before the steps,
      session not read-only, `top_n` ignored, exceptions escaping) each caught
      (my first "report before test" mutation was invalid code and did not
      count; it was redone). **End to end on the scratch database** with the
      real `run_transform()` and real dbt: version line first, seed 3/3, run
      14/14, test 88 pass + 6 warn + 0 error (the warns are the undated show,
      NULL years and similar expected ones), then the report. Its numbers match
      a hand count: Metallica 10 performances / 6 matched / 2 with a year / 4
      without (*Master of Puppet* x3, *Helpless (jam)* x1) / 4 unmatched
      (*Made Up Metal Jam* x3, plus a title containing a line break printed on
      one line); Oasis 6 / 4 / 3 / 1 (*Ain't Got Nothing*) / 2; the undated
      show is excluded.
      **Where the lists live — needs your decision.** Task logs are files in
      the `airflow-logs` volume; the `log_cleanup` DAG deletes logs older than
      14 days but is **paused** here, so setlist titles with counts stay on
      disk until someone deletes them or unpauses it. With `airflow dags test`
      the output goes to the terminal / a redirect file instead. Documented in
      `dbt/README.md`; nothing was changed about retention.
- [x] **R3-3. Recordings without a release date stay in the catalog.** No
      change; to be decided after tomorrow's numbers.
- [x] **Docs.** `dbt/README.md` section on the log-only report; root README
      notes that `make` is available in WSL (`sudo apt install make`).

### Tomorrow's checklist (in this order)

Timing first: setlist.fm's 1,440/day may be a rolling 24 h window rather than
a calendar day. Today's 1,205 requests happened between about 16:47 and 18:05
UTC, so start the run **after about 18:10 UTC** (15:10 in Brazil); a
calendar-day reset would allow any time. The run costs about 481 requests.

1. **Rebuild the image** (repo root; `make` works in WSL, otherwise use the
   docker command in the comment):

       export DBT_GIT_COMMIT="$(git log -1 --format=%h -- dbt)$(git diff --quiet HEAD -- dbt || echo -dirty)"
       make build      # docker compose -f infra/docker-compose.yml --env-file .env build
       make up         # plain, NOT up-dev: the run must use the baked copy

2. **Confirm the dbt version line** (the same function the transform logs first):

       docker exec infra-airflow-scheduler-1 python -c "import logging; logging.basicConfig(level=logging.INFO, format='%(message)s'); from encore.dbt_runner import log_dbt_project_version as f; f()"
       git log -1 --format=%h -- dbt     # must equal commit=, with no -dirty
       docker exec infra-airflow-scheduler-1 grep -c aged_performances /opt/airflow/dbt/models/analytics/mart_repertoire_age.sql   # expect 1

   (In Git Bash prefix `docker exec` commands that take `/opt/...` paths with
   `MSYS_NO_PATHCONV=1`; not needed in WSL.)

   Then the budget (expect 0 or a small number today, plus about 481, at most 1300):

       docker exec infra-postgres-1 psql -U "$POSTGRES_USER" -d encore -tAc "select coalesce(sum(setlistfm_requests),0) from ops.pipeline_runs where finished_at::date = current_date"

3. **Run the full pipeline** with the DAG paused and `ENCORE_BANDS_FILTER`
   empty, output to a file **outside the repo** (it will contain setlist
   titles; delete it afterwards). Use a logical date not used before:

       docker exec infra-airflow-scheduler-1 airflow dags test encore_pipeline 2026-09-25 > <scratch>/run.log 2>&1

4. **Report**, from that log and the database:
   - reconciliation: `grep -E "assert_marts_reconcile|assert_no_undated|Done. PASS" run.log`
   - *Let There Be Love* at 2005 and an empty audit:

         select song_title, release_year, album_year, recording_year, release_year_fixed
           from intermediate.int_song_catalog
          where band = 'Oasis' and song_title = 'Let There Be Love';    -- 2005 | 2005 | 2001 | t
         select count(*) from intermediate.int_song_release_date_audit;  -- 0

     and `assert_song_recording_date_not_far_before_album` passing in the log.
   - `aged_performances` share per band:

         select band, sum(performances) performances, sum(matched_performances) matched,
                sum(aged_performances) aged,
                round(100.0 * sum(aged_performances) / sum(performances), 2) aged_pct_of_performances,
                round(100.0 * sum(aged_performances) / sum(matched_performances), 2) aged_pct_of_matched,
                round(100.0 * (sum(matched_performances) - sum(aged_performances)) / sum(performances), 2) matched_without_year_pct
           from analytics.mart_repertoire_age
          group by band order by matched_without_year_pct desc;

   - the two lists per band: `grep -F "[report]" run.log`.
5. **Then delete `run.log`** (task-log retention is settled: 7 days, see the
   decisions above). The catalog decision (R3-3) waits for these numbers.

### Decisions on the round-3 open points (2026-09-21)

- **Keep the report running even when `dbt test` fails** (as built): no code
  change. It still does not run if `seed` or `run` failed.
- **`log_cleanup` unpaused and retention 7 days instead of 14.**
  `MAX_LOG_AGE_DAYS = 7` (`src/encore/log_cleanup.py`; the default-threshold
  test now checks an 8-day file is deleted and a 6-day file kept; going back
  to 14 makes it fail). `log_cleanup` now has `is_paused_upon_creation=False`
  (an addition to what was asked: without it the retention would depend on a
  manual unpause on every machine, including the VM where DAGs are created
  paused). README, `dbt/README.md` and `docs/methodology.md` updated. The
  spec-01 text (R1.6, 14 days) is left as the historical record; this entry
  is the change. No pipeline run today; tomorrow's run starts after 18:10 UTC.
  **Verified for real.** Image rebuilt (constant 7 inside it). The existing
  `log_cleanup` DAG stayed paused after the rebuild, as expected
  (`is_paused_upon_creation` only applies to DAGs created afterwards), so it
  was unpaused once with `airflow dags unpause log_cleanup`. With two probe
  files planted in the logs volume (8 and 6 days old; no real log was older
  than 7 days), the scheduler's run succeeded, logged "Deleted 1 log file(s)
  older than 7 days", removed the 8-day file and the directory it left empty
  and kept the 6-day one; the probe was then removed. Final state:
  `log_cleanup` active, `encore_pipeline` paused. pytest 83 passed.

### Bug found and fixed before today's run (2026-09-22)

`check_api_budget` failed immediately: "Projected setlist.fm requests today
(1495 = 1012 already logged + 483 estimated) would exceed the daily budget of
1300." Real usage today was 0 (confirmed via `finished_at::date`). Cause:
`ops.sum_setlistfm_requests_today()` filters on `started_at`, and for a DAG
run started with `airflow dags test <date>`, `started_at` is the **logical
date passed on the command line**, not the real wall clock — a quirk already
noted after item 22 as "cosmetic". During yesterday's verification I ran
`airflow dags test encore_pipeline 2026-09-22/2026-09-23/2026-09-24` (picking
unused future logical dates so as not to collide with real runs), which left
3 rows in `ops.pipeline_runs` with `started_at` on those future dates —
today, that placed 1,012 of yesterday's real requests inside "today"'s
window. **Not cosmetic after all: it can block a legitimate run.**
Fix applied: `update ops.pipeline_runs set started_at = finished_at where
started_at::date <> finished_at::date` (4 rows, all mine from yesterday's
testing) — corrects the date without deleting any row or request count.
Today's logged total is 0 again. **Follow-up to consider:** `check_api_budget`
should compare against `finished_at` (or the DAG run's real `logical_date`
under its normal `@monthly` schedule, not a manually-supplied test date), so
a test run's logical date can never again collide with a later real day. Not
fixed now; flagged for the project owner.

### Full 7-band run, 2026-09-22 — checklist completed

Same-day sequence: rebuilt the image at HEAD `9f84a4c` (the running one was
stale, `commit=262af17-dirty`, from before yesterday's retention change —
caught before running anything real). First attempt (`airflow dags test
encore_pipeline 2026-09-26`) failed at `check_api_budget`: "Projected
requests today (1495 = 1012 already logged + 483 estimated) would exceed
1300." **Bug found and fixed** (see `spec-02a-followup-progress.md`,
"Bug found and fixed before today's run"): `sum_setlistfm_requests_today()`
filters on `started_at`, which for `airflow dags test <date>` is the logical
date on the command line, not the wall clock; three rows from yesterday's
testing had future logical dates (`2026-09-22/23/24`) that landed inside
today's window. Corrected `started_at = finished_at` for the 4 mis-dated rows
(no request counts changed); today's logged total went back to 0. Re-ran with
logical date `2026-09-22` (today, for real): **success**, all 14 tasks ok,
`raw_setlistfm` 0 / 0 / 0, 481 setlist.fm requests, dbt seed 3/3, run 14/14,
**test 92 pass + 2 warn** (the two by-design NULL-year warnings, both smaller
than before: 457 songs, down from catalog rows including the fixed song).

**Reconciliation:** `assert_marts_reconcile_with_int_performances` PASS,
`assert_no_undated_performances_left_out_of_marts` PASS.

**Let There Be Love:** `release_year=2005, album_year=2005,
recording_year=2001, release_year_fixed=true`. Audit list: 0 rows.

**`aged_performances` share per band** (the real answer to the
follow-up-3 question, replacing yesterday's upper-bound estimate):

| Band | Performances | Matched | Aged | Matched w/o year |
|---|---|---|---|---|
| Muse | 23,334 | 23,094 | 22,931 | 0.70% |
| Arctic Monkeys | 15,945 | 15,861 | 15,838 | 0.14% |
| Linkin Park | 16,886 | 16,464 | 16,464 | 0.00% |
| Metallica | 34,019 | 34,016 | 34,015 | 0.00% |
| Avenged Sevenfold | 10,756 | 10,628 | 10,628 | 0.00% |
| Twenty One Pilots | 16,722 | 16,545 | 16,545 | 0.00% |
| Oasis | 11,969 | 11,968 | 11,968 | 0.00% |

**No band exceeds 2%** (the highest is Muse at 0.70%). This is much lower than
the 3.1-13.1% upper bounds reported yesterday (`match_rate_by_performance -
match_rate_by_album`, which conflated "no album" with "no year"): most
recording-only songs turn out to have a usable release year from their
earliest MusicBrainz recording. **Decision this answers (R3-3 / follow-up-3):
recordings without a release date stay in the catalog** — excluding them
would only affect a handful of songs (all recording-only, undated), well
under any reasonable threshold, and 6 of 7 bands are unaffected entirely.

**Match rates per band** (`match_rate_by_performance` / `match_rate_by_album`):
Oasis 0.9999/0.8689, Metallica 0.9999/0.9364, Arctic Monkeys 0.9947/0.9511,
Muse 0.9897/0.9313 (2 years below 0.90: the known 1994-95 limitation),
Twenty One Pilots 0.9894/0.9462, Avenged Sevenfold 0.9881/0.9572, Linkin Park
0.9750/0.9149. No band below 0.90 overall.

**The two lists per band** (task log only; the full run log,
`run_final2.log`, has been **deleted** after this summary was written, per
the checklist). Top undated-catalog-song and top-unmatched-title, by band:

- **Arctic Monkeys** — undated: *Sandtrap* (23, recording). Unmatched: *Drawbridge* (59), *Little Illusion Machine (Wirral Riddler)* (13), *Put Me in a Terror Pocket* (10), plus 2 singles.
- **Avenged Sevenfold** — undated: none. Unmatched: *Band Jam Session* (105), *Drum Solo* (21), 2 singles.
- **Linkin Park** — undated: none. Unmatched: *Joe Hahn Solo* (170), *Remember the Name* (151 — a real song not yet in the catalog), *Mashup Intro #2* (48), *It's Goin' Down* (40), *Mashup Intro #1* (12), 1 single.
- **Metallica** — undated: *Are You Gonna Go My Way* (1, recording — a cover, oddly catalogued). Unmatched: 3 one-off covers (*Beat It*, *Seven Nation Army*, *Smells Like Teen Spirit*).
- **Muse** — undated: *Munich Jam* (163, recording). Unmatched: 20 entries, almost all jams/soundchecks by city name (*Monty Jam* 103, *Houston Jam* 53, *MK Jam* 19, *Osaka Jam* 15, ...) plus a few real-looking titles (*Weakening Walls* 6, *Cut Me Down* 3, *Small Minded* 3) that may be legitimate rarities missing from the catalog.
- **Oasis** — undated: none. Unmatched: *Chipper S.O.B.* (1, the one known from spec-02a).
- **Twenty One Pilots** — undated: none. Unmatched: covers dominate — *Home* (40), *I Can See Clearly Now* (40), *My Girl* (39), *Stolen Dance* (21), *Careless Whisper* (5), plus one-offs.

**Follow-up spotted, not fixed:** `check_api_budget` should compare against
`finished_at` (or a real DAG-run `logical_date` under the `@monthly` schedule)
rather than a manually supplied test date, so a future test run can't collide
with a later real day again. Flagged in `spec-02a-followup-progress.md`.
