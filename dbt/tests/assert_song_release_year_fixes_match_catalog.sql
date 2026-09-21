-- A year fix must point at a song that exists in the catalog for that band.
-- Otherwise it is a typo that changes nothing and nobody would notice.
-- Only checked for bands that have catalog rows loaded at all, so seeding a
-- fix for a band not yet ingested does not fail. Passes when it returns no rows.
select
    o.band,
    o.canonical_song_title,
    o.first_release_year
from {{ ref('seed_song_overrides') }} as o
where nullif(btrim(o.first_release_year), '') is not null
  and exists (select 1 from {{ ref('int_song_catalog') }} as c where c.band = o.band)
  and not exists (
        select 1 from {{ ref('int_song_catalog') }} as c
        where c.band = o.band
          and c.title_normalized = {{ normalize_title('o.canonical_song_title') }}
      )
