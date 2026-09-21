-- WARN-level review list (product.md, "Suspicious release dates"): songs
-- whose recording date is more than 2 years before the album year. A warning
-- here is not a failure — it means "these MusicBrainz dates need a human
-- look". List them with:
--   select * from intermediate.int_song_release_date_audit;
-- then keep them, or fix a year through seed_song_overrides.first_release_year.
{{ config(severity='warn') }}

select * from {{ ref('int_song_release_date_audit') }}
