# Spec 02a: Minimal dbt layer and the first KPI

Read the context files in `docs/context/` before starting. This is a vertical slice of spec 02: only what is needed to produce one KPI end to end, so the model can be validated against real data before the full modeling work.

## Goal

Inside a single pipeline run, transform the ephemeral setlist.fm data plus the persistent MusicBrainz data into one aggregated mart, `analytics.mart_repertoire_age`, and chart it in a notebook.

The KPI: **average repertoire age**, the mean of (show year minus song release year) over the catalog songs played in a show, aggregated by band, tour and year.

## Requirements

### R1. dbt project
1. dbt project under `dbt/`, profile targeting the `encore` database, using environment variables for credentials.
2. Schemas by layer: `staging` and `intermediate` materialized as **views**, `analytics` as **tables**. No exceptions, because views over `raw_setlistfm` must break harmlessly once the raw data is deleted.
3. `dbt/seeds/` with two seed files:
   - `seed_album_exclusions.csv`: band, album title. Preloaded with the 5 entries validated in Phase 0 (Oasis Manchester 1994, Oasis Eden Project 2009, Muse The Resistance Instrumentals, Avenged Sevenfold St. Louis 2009, Metallica Lulu).
   - `seed_song_overrides.csv`: band, raw song name, canonical song title, album title. Empty except for a header, to be filled as mismatches are found.
4. `dbt/README.md` explaining how to run dbt locally and inside Airflow.

### R2. Staging models (views)
1. `stg_setlists`: one row per show, from `raw_setlistfm.setlists`. Columns: setlist_id, band, show_date, show_year, tour_name, venue, city, country, setlist_url.
2. `stg_setlist_entries`: one row per performed song, from `raw_setlistfm.setlist_entries`. Medleys split on " / " into separate rows, keeping the original position and adding `is_medley`. Columns: setlist_id, band, song_name_raw, position, set_index, is_encore, is_cover, is_tape, is_medley.
3. `stg_albums` and `stg_album_tracks` from `raw_musicbrainz`, with album exclusions applied from the seed.
4. `stg_recordings` from `raw_musicbrainz`, deduplicated by normalized title keeping the earliest release date.

### R3. Normalization
1. A dbt macro `normalize_title(column)` implementing the Phase 0 rules: lowercase, strip accents, remove apostrophes without inserting a space, replace `&` with `and`, remove punctuation, collapse whitespace, strip suffixes such as remastered, live, demo, edit, and `feat.` segments.
2. Used on both sides of every title match.

### R4. Intermediate models (views)
1. `int_song_catalog`: one row per distinct catalog song per band, with canonical title, reference album (earliest studio album containing it), release year (from the album when matched, otherwise from the recording), and `catalog_source` (album, recording, override).
2. `int_performances`: one row per performed song joined to `int_song_catalog`. Excludes entries where `is_tape` or `is_cover` is true. Flags `is_matched` when the song resolved to the catalog.
3. Song overrides from the seed take precedence over automatic matching.

### R5. Mart (table, persistent)
`analytics.mart_repertoire_age`, grain: band, tour, year.

Columns: band, tour_name, show_year, shows, performances, matched_performances, match_rate, avg_repertoire_age, median_repertoire_age, oldest_song_year, newest_song_year, computed_at.

Rules:
- Repertoire age of a performance: show_year minus song release year.
- Only matched, non-tape, non-cover performances enter the average.
- Shows with no tour name are grouped under the literal `Unknown tour` in this slice. Tour inference is out of scope here.
- **The mart must not contain any setlist id, show date, venue or song title.** It is aggregated data only.

### R6. Data quality mart
`analytics.mart_match_quality`, grain: band and year. Columns: band, show_year, performances, matched_performances, match_rate_by_performance, distinct_songs, distinct_songs_matched, match_rate_by_title, computed_at.

This is the metric that tells whether the matching is good enough, weighted by plays.

### R7. dbt tests
1. `not_null` and `accepted_values` where applicable on staging models.
2. A singular test asserting that no model in `analytics` exposes a column named `setlist_id`, `show_date`, `venue` or `song_name_raw`.
3. A singular test asserting `avg_repertoire_age` is never negative.
4. A singular test asserting `match_rate` is between 0 and 1.

### R8. Airflow integration
1. Replace the `transform` placeholder task in `encore_pipeline` with real steps: `dbt seed` (only when seeds changed or on first run), `dbt run`, `dbt test`.
2. dbt runs **before** `cleanup_raw_setlistfm`, in the same DAG run.
3. A dbt failure fails the DAG, and cleanup still runs (trigger rule unchanged).
4. dbt logs are visible in the Airflow task logs.

### R9. Notebook
`notebooks/01_first_kpi.ipynb`, reading **only** from `analytics`:
1. Line chart of average repertoire age by year, one line per band present in the data.
2. Bar chart of average repertoire age by tour for one band.
3. Table of match quality by band and year.
4. Outputs cleared before committing.

## Acceptance criteria

- A full DAG run with `ENCORE_BANDS_FILTER=Oasis` ends with `analytics.mart_repertoire_age` populated and `raw_setlistfm` empty.
- `match_rate_by_performance` for Oasis is at least 0.90. If it is lower, list the top unmatched titles by play count so they can be added to the override seed.
- All dbt tests pass.
- Running the DAG twice produces the same mart contents (idempotent), with `computed_at` updated.
- The notebook renders both charts from the marts alone, with no access to raw data.

## Out of scope (full spec 02 and 03)

- Tour inference for shows without a tour name
- Rotation (Jaccard), survival analysis, set position and geography KPIs
- Remaining marts from the project brief
- API and frontend
