-- Tracks of each studio album's representative release, from
-- raw_musicbrainz.album_tracks (spec-02a R2.3). Inner-joined to
-- stg_albums so a track of an excluded album is dropped with its album.
-- `track_title_normalized` is carried here so the intermediate layer can
-- join to setlist songs without re-normalizing.

with tracks as (

    select * from {{ source('raw_musicbrainz', 'album_tracks') }}

)

select
    a.band,
    a.release_group_mbid,
    a.album_title,
    a.release_year as album_release_year,
    t.recording_mbid,
    t.title as track_title,
    {{ normalize_title('t.title') }} as track_title_normalized,
    t.track_position
from tracks as t
inner join {{ ref('stg_albums') }} as a
    on a.release_group_mbid = t.release_group_mbid
