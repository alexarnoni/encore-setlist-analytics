# Spec 03: Rotation and song survival

Read the context files in `docs/context/` and `docs/methodology.md` before starting. This spec adds two KPIs on top of the dbt layer from spec 02a: how much a band's setlist changes between shows (rotation) and how long songs stay in the live repertoire (survival).

## Working rules for this spec

- Work on a branch named `spec-03`. Do not merge into the main branch until the next full pipeline run on the main branch has passed its checklist.
- No setlist.fm requests. Develop and test with synthetic setlists in a disposable database, the same way spec 02a follow-up was validated.
- Do not change the image, the DAG or the dbt models used by the main branch outside this branch.

## Part A: Rotation

### Definitions
- **Setlist set** of a show: the distinct canonical catalog songs played, excluding tape and covers, and excluding unmatched titles.
- **Jaccard similarity** between two shows: size of the intersection of their sets divided by the size of the union.
- **Consecutive pair**: two shows of the same band, same tour, adjacent in date order. Shows with the tour `Unknown tour` are excluded from pairs.
- **Rotation** of a tour: 1 minus the mean Jaccard similarity over its consecutive pairs.
- **Core songs** of a tour: songs present in at least 90% of the tour's shows.
- Tours with fewer than 5 shows with at least one matched song are excluded from rotation metrics.

### Requirements
1. Intermediate view `int_show_song_sets`: one row per show and canonical song (show key, band, tour, show date, song key). It is a view over raw data and is never persisted.
2. Intermediate view `int_show_pairs`: consecutive pairs with their Jaccard similarity.
3. Mart `analytics.mart_tour_rotation`, grain band and tour. Columns: band, tour_name, first_year, last_year, shows, pairs, mean_jaccard, rotation, median_setlist_size, core_songs, distinct_songs, computed_at.
4. Mart `analytics.mart_band_rotation_by_year`, grain band and year, weighted by pairs. Columns: band, show_year, pairs, mean_jaccard, rotation, computed_at.
5. No show key, date, venue or raw title in either mart.

### Expected sanity checks
- Metallica should show higher rotation than Muse in recent tours (Metallica's M72 tour played two different sets per city).
- Rotation must lie between 0 and 1.

## Part B: Song survival

### Definitions
- Time is measured in **band shows**, not calendar time, so hiatuses do not count as abandonment.
- Show index: position of the show in the band's full chronological show history (shows with at least one matched song).
- **Live debut** of a song: the first show index where it was played.
- **Gap**: a run of at least N = 50 consecutive shows, all inside the band's history, without the song. A gap between two appearances is an **intermediate gap** (the song returned); the run after the last appearance is the **final gap**.
- **Abandonment event**: the **final gap** only. The song is abandoned when its last appearance is at least N shows before the end of the band's history, i.e. it left the setlist and did not return. Duration = shows from live debut to that last appearance (inclusive).
- **Censored**: every other song: still played (last appearance fewer than N shows before the end of the history), or it left and came back. Duration = shows from live debut to its last appearance (the same rule as for an event; it is not extended to the end of the history).
- `returned_after_abandonment` is true when the song had at least one intermediate gap, and `gaps_count` is the number of intermediate gaps. Both are independent of the event.
- *Changed 2026-09-23:* the first version counted the first gap as the event, which turned songs that were dropped for a while and brought back into abandonments even when still played today. Duration was also unified: every song, event or censored, runs from debut to its last appearance.
- Eligible songs: catalog songs with at least 3 performances. Non-album songs are included under the album label `non-album`.

### Requirements
6. Python module `src/encore/analysis/survival.py` that:
   - reads the per-show song sets from `int_show_song_sets` during the pipeline run;
   - computes duration, event and censoring per song for N = 25, 50 and 100;
   - fits Kaplan-Meier curves with lifelines per band, and per band and reference album;
   - writes only aggregated results to `analytics`.
7. Mart `analytics.mart_song_survival`, grain band and song (canonical MusicBrainz title). Columns: band, song_title, reference_album, release_year, performances, debut_year, last_year, duration_shows_n50, event_n50, returned_after_abandonment, gaps_count, computed_at. Years only, never full dates.
8. Mart `analytics.mart_survival_curves`, grain band, album (or `all`), N and time step. Columns: band, album, n_window, t_shows, at_risk, events, survival_probability, ci_lower, ci_upper, computed_at.
9. Mart `analytics.mart_survival_summary`, grain band, album (or `all`) and N. Columns: band, album, n_window, songs, events, censored, median_survival_shows (null when the curve never drops below 0.5), computed_at.
10. New Airflow task `analyze` between `transform` and `cleanup_raw_setlistfm`. It runs the Python module after dbt, fails the DAG on error, and cleanup still runs.
11. dbt sources or exposures documenting the three survival marts, and dbt tests on them: survival_probability between 0 and 1 and non-increasing in t_shows per curve, events plus censored equal to songs.

### Expected sanity checks
- Songs from debut albums that are still played today (for example Metallica's Master of Puppets era, Oasis's Definitely Maybe) are censored with very long durations.
- Results for N = 25, 50 and 100 differ, but not drastically, as in Phase 0.

## Part C: Tests
12. Unit tests for the survival module with hand-built show histories: a song abandoned exactly at the window, a censored song, a song that returns after abandonment, a band with a long hiatus (no false abandonment).
13. Unit test for Jaccard on known sets.
14. The forbidden columns test from spec 02a extended to the new marts.
15. Reconciliation test: songs in `mart_song_survival` per band equal eligible catalog songs in `int_performances`.

## Part D: Notebook
16. `notebooks/02_rotation_survival.ipynb`, reading only from `analytics`:
   - rotation by year, small multiples, one panel per band, same y scale;
   - Kaplan-Meier curves for one band, one line per album, with confidence bands;
   - table of median survival by band and album for N = 50.
   Outputs cleared before committing. An executed HTML may be generated into `reports/`.

## Acceptance criteria
- All tests pass on synthetic data in the disposable database.
- After merge, a full pipeline run produces all new marts, dbt tests pass, raw_setlistfm ends empty.
- The sanity checks above hold on real data, or the deviation is explained.

## Out of scope
- Tour inference for shows without a tour name
- Set position (opener, closer, encore) and geography KPIs
- API and frontend
