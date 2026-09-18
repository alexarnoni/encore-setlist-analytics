-- One row per distinct catalog song per band (spec-02a R4.1).
-- Key: (band, title_normalized).
--
-- Three sources, with PRECEDENCE override > album > recording (R4.3: seed
-- overrides beat automatic matching):
--
--   override   a seed_song_overrides row with an album_title: the song's
--              reference album — and so its release year — is that album,
--              looked up in stg_albums.
--   album      the song is a track on a kept studio album. Reference album
--              is the EARLIEST studio album containing it; release year is
--              that album's year (R4.1: "from the album when matched").
--   recording  no album has it, but MusicBrainz has a recording of it:
--              release year is the recording's earliest year, no album.
--
-- release_year is NULL when the source has no usable date; NULL years
-- can't enter the repertoire-age average (see spec-02a-progress.md).

with album_candidates as (

    select
        band,
        track_title_normalized as title_normalized,
        track_title as song_title,
        album_title as reference_album,
        album_release_year as release_year,
        row_number() over (
            partition by band, track_title_normalized
            order by album_release_year asc nulls last, album_title, release_group_mbid
        ) as rn
    from {{ ref('stg_album_tracks') }}

),

album_songs as (

    select
        band, title_normalized, song_title, reference_album, release_year,
        'album'::text as catalog_source
    from album_candidates
    where rn = 1

),

override_candidates as (

    select
        o.band,
        {{ normalize_title('o.canonical_song_title') }} as title_normalized,
        o.canonical_song_title as song_title,
        coalesce(a.album_title, o.album_title) as reference_album,
        a.release_year,
        row_number() over (
            partition by o.band, {{ normalize_title('o.canonical_song_title') }}
            order by o.album_title, o.raw_song_name
        ) as rn
    from {{ ref('seed_song_overrides') }} as o
    left join {{ ref('stg_albums') }} as a
        on a.band = o.band
       and {{ normalize_title('a.album_title') }} = {{ normalize_title('o.album_title') }}
    -- blank album_title = an alias only (raw name -> canonical); it does
    -- not create a catalog row, item 13 applies it when matching.
    where nullif(btrim(o.album_title), '') is not null

),

override_songs as (

    select
        band, title_normalized, song_title, reference_album, release_year,
        'override'::text as catalog_source
    from override_candidates
    where rn = 1

),

recording_songs as (

    select
        r.band,
        r.title_normalized,
        r.title as song_title,
        null::text as reference_album,
        r.release_year,
        'recording'::text as catalog_source
    from {{ ref('stg_recordings') }} as r
    where not exists (
        select 1 from album_songs as a
        where a.band = r.band and a.title_normalized = r.title_normalized
    )

),

combined as (

    select * from override_songs

    union all

    select * from album_songs as a
    where not exists (
        select 1 from override_songs as o
        where o.band = a.band and o.title_normalized = a.title_normalized
    )

    union all

    select * from recording_songs as r
    where not exists (
        select 1 from override_songs as o
        where o.band = r.band and o.title_normalized = r.title_normalized
    )

)

select
    band,
    title_normalized,
    song_title,
    reference_album,
    release_year,
    catalog_source
from combined
