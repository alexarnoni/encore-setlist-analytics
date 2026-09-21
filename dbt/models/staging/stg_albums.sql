-- Studio albums from raw_musicbrainz.albums (spec-02a R2.3), minus the
-- manually excluded ones in seed_album_exclusions (wrong classification
-- in MusicBrainz, or a live/bootleg release filed as an album).
--
-- Exclusions are matched per band on normalize_title() of BOTH sides
-- (R3.2), so a curly-vs-straight apostrophe or a remaster suffix can't
-- make an exclusion silently miss. tests/assert_album_exclusions_match_
-- when_band_loaded.sql fails if an exclusion for a loaded band matches
-- nothing, so a miss can't go unnoticed.

with albums as (

    select * from {{ source('raw_musicbrainz', 'albums') }}

),

exclusions as (

    select
        band,
        {{ normalize_title('album_title') }} as title_normalized
    from {{ ref('seed_album_exclusions') }}

)

select
    a.release_group_mbid,
    a.band_mbid,
    a.band_name as band,
    a.title as album_title,
    a.first_release_date,
    {{ release_year('a.first_release_date') }} as release_year
from albums as a
where not exists (
    select 1
    from exclusions as x
    where x.band = a.band_name
      and x.title_normalized = {{ normalize_title('a.title') }}
)
