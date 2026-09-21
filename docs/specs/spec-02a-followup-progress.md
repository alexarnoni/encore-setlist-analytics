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
- [ ] **7. Rerun dbt on the current Oasis data** and report how
      `avg_repertoire_age` changed.
- [ ] **8. Full pipeline, all 7 bands** (`ENCORE_BANDS_FILTER` empty), after
      a setlist.fm request-budget check.
- [ ] **9. Report** per-band `match_rate_by_performance` and
      `match_rate_by_album`, songs flagged by the date check, and top 20
      unmatched titles for any band below 0.90. **Stop for review.**

## Log
