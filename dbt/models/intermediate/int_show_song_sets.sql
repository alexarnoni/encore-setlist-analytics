-- The setlist set of every show: one row per show and distinct canonical
-- catalog song (spec-03 R1). Input of the rotation models and of the survival
-- module.
--
-- * Only MATCHED songs: tape entries and covers are already left out of
--   int_performances, and unmatched titles are dropped here (`is_matched`), so
--   a set is "the distinct canonical catalog songs played".
-- * Shows without a usable date are left out: they cannot be ordered.
-- * `show_key` is the setlist id. That is fine in `intermediate` (a view over
--   ephemeral raw data) and is never carried into `analytics`.
-- * A show with no tour on setlist.fm gets the label 'Unknown tour', as in
--   mart_repertoire_age; the rotation models exclude it from pairs, but it
--   stays in the band's show history for survival.
--
-- Like every model over int_performances it is a view over EPHEMERAL data:
-- nothing here is persisted.
-- PERFORMANCE: `materialized` is deliberate. Filtering the int_performances
-- view directly on `is_matched` makes Postgres reorder its joins and
-- re-evaluate the stg_setlists view (with its date parsing) once per entry:
-- over 4 minutes at the size of a real run (~130k entries) against ~4 seconds
-- when int_performances is computed first and filtered afterwards.
with performances as materialized (

    select
        setlist_id,
        band,
        tour_name,
        show_date,
        title_normalized,
        song_title,
        is_matched
    from {{ ref('int_performances') }}

)

select distinct
    setlist_id as show_key,
    band,
    coalesce(tour_name, 'Unknown tour') as tour_name,
    show_date,
    title_normalized as song_key,
    song_title
from performances
where is_matched
  and show_date is not null
