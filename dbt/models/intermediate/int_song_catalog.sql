-- One row per distinct catalog song per band (spec-02a R4.1).
-- Key: (band, title_normalized).
--
-- Three sources, with PRECEDENCE override > album > recording (R4.3: seed
-- overrides beat automatic matching):
--
--   override   a seed_song_overrides row with an album_title: the song's
--              reference album is that album, looked up in stg_albums.
--   album      the song is a track on a kept studio album. Reference album
--              is the EARLIEST studio album containing it.
--   recording  no album has it, but MusicBrainz has a recording of it: no
--              reference album.
--
-- RELEASE YEAR (product.md, "Song release year"): a song's first OFFICIAL
-- release year is the earliest of its reference album's year and its
-- recording's first-release year (`least` ignores a missing side). The
-- reference album stays the basis for era KPIs; only the year used for
-- repertoire age changes. album_year and recording_year are kept beside
-- release_year so a suspicious date can be seen and audited
-- (int_song_release_date_audit).
--
-- A seed_song_overrides row with a first_release_year (and blank raw name
-- and album) FIXES a wrong MusicBrainz date: that year replaces the
-- computed one for the song and release_year_fixed is true.
--
-- release_year is NULL when no source has a usable date; NULL years can't
-- enter the repertoire-age average (see spec-02a-progress.md).

with album_candidates as (

    select
        band,
        track_title_normalized as title_normalized,
        track_title as song_title,
        album_title as reference_album,
        album_release_year as album_year,
        row_number() over (
            partition by band, track_title_normalized
            order by album_release_year asc nulls last, album_title, release_group_mbid
        ) as rn
    from {{ ref('stg_album_tracks') }}

),

album_songs as (

    select
        band, title_normalized, song_title, reference_album, album_year,
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
        a.release_year as album_year,
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
        band, title_normalized, song_title, reference_album, album_year,
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
        null::int as album_year,
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

),

-- One computed year fix per (band, canonical title). A malformed year is
-- ignored here and fails assert_song_release_year_fixes_valid.
year_fixes as (

    select
        band,
        {{ normalize_title('canonical_song_title') }} as title_normalized,
        first_release_year::int as fixed_year,
        row_number() over (
            partition by band, {{ normalize_title('canonical_song_title') }}
            order by first_release_year
        ) as rn
    from {{ ref('seed_song_overrides') }}
    where first_release_year ~ '^[1-9][0-9]{3}$'
      and nullif(btrim(canonical_song_title), '') is not null

)

select
    c.band,
    c.title_normalized,
    c.song_title,
    c.reference_album,
    coalesce(f.fixed_year, least(c.album_year, r.release_year)) as release_year,
    c.catalog_source,
    c.album_year,
    r.release_year as recording_year,
    f.fixed_year is not null as release_year_fixed
from combined as c
left join {{ ref('stg_recordings') }} as r
    on r.band = c.band
   and r.title_normalized = c.title_normalized
left join year_fixes as f
    on f.band = c.band
   and f.title_normalized = c.title_normalized
   and f.rn = 1
