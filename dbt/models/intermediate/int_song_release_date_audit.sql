-- Songs whose MusicBrainz recording date looks suspicious: the earliest
-- recording is MORE THAN 2 YEARS before the reference album's year
-- (product.md, "Suspicious release dates"). Because a song's release year
-- is the earlier of the two, such a recording date pulls the song's
-- repertoire age up, so each row deserves a look — a legitimate early demo
-- or a wrong date.
--
-- To settle a row, add a seed_song_overrides row with band,
-- canonical_song_title and first_release_year (raw_song_name and
-- album_title blank). The song then has release_year_fixed = true and drops
-- off this list.
--
-- Built only from MusicBrainz data (no setlist.fm), so it is safe to query
-- at any time, including when raw_setlistfm is empty.
select
    band,
    song_title,
    reference_album,
    album_year,
    recording_year,
    album_year - recording_year as years_earlier,
    release_year as applied_release_year
from {{ ref('int_song_catalog') }}
where not release_year_fixed
  and album_year is not null
  and recording_year is not null
  and album_year - recording_year > 2
