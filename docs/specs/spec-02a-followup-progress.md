# Spec 02a — Follow-up after acceptance

Work requested by the project owner when accepting spec 02a
(`docs/specs/spec-02a-progress.md`, now closed). Same discipline: one
commit per item, results recorded here.

## Checklist

- [x] **1. Close `spec-02a-progress.md`** and record both decisions —
      status banner added, acceptance and the two decisions logged.
- [ ] **2. `docs/context/product.md`** — album metric / "non-album"
      category and the first-official-release-year rule under *Key metric
      rules*.
- [ ] **3. Release year = first official release year** in
      `int_song_catalog`, plus a warn-level audit of suspicious
      recording dates and a way to fix a year through the override seed.
- [ ] **4. `match_rate_by_album`** in `mart_match_quality` (informational).
- [ ] **5. Notebook: legend upper left** instead of direct labels.
- [ ] **6. Notebook: years with fewer than 3 shows** as hollow markers,
      left out of the connecting line, rule noted under the title.
- [ ] **7. Rerun dbt on the current Oasis data** and report how
      `avg_repertoire_age` changed.
- [ ] **8. Full pipeline, all 7 bands** (`ENCORE_BANDS_FILTER` empty), after
      a setlist.fm request-budget check.
- [ ] **9. Report** per-band `match_rate_by_performance` and
      `match_rate_by_album`, songs flagged by the date check, and top 20
      unmatched titles for any band below 0.90. **Stop for review.**

## Log
