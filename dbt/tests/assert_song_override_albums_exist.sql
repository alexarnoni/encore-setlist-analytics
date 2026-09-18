-- A song override that names an album MusicBrainz/stg_albums doesn't have
-- would silently produce a catalog row with a NULL release year (spec-02a
-- item 12) — the override "works" but the song can never be aged. So: an
-- override with an album_title must match a kept studio album of that band.
--
-- Bands with no albums loaded are skipped (can't be checked yet), same
-- limitation, and same reasoning, as assert_album_exclusions_match_when_
-- band_loaded. Passes when it returns no rows.
select
    o.band,
    o.raw_song_name,
    o.album_title
from {{ ref('seed_song_overrides') }} as o
where nullif(btrim(o.album_title), '') is not null
  and exists (
        select 1 from {{ ref('stg_albums') }} as a where a.band = o.band
    )
  and not exists (
        select 1 from {{ ref('stg_albums') }} as a
        where a.band = o.band
          and {{ normalize_title('a.album_title') }} = {{ normalize_title('o.album_title') }}
    )
