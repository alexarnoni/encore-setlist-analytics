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

