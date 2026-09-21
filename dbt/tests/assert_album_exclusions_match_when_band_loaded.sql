-- Guards against a silently useless exclusion (spec-02a item 9).
-- If MusicBrainz renames an album, or a seed row has a typo, the
-- exclusion would match nothing and the unwanted album would flow into
-- the marts with no error. So: every exclusion whose band HAS albums in
-- raw_musicbrainz must match at least one of them.
--
-- Bands with no albums loaded yet are skipped — an exclusion for
-- Metallica can't be checked while only Oasis is in the database. That
-- makes this a no-op for those rows until their data arrives, not a
-- pass; it starts guarding them the first run they are loaded.
select
    x.band,
    x.album_title
from {{ ref('seed_album_exclusions') }} as x
where exists (
        select 1 from {{ source('raw_musicbrainz', 'albums') }} as a
        where a.band_name = x.band
    )
  and not exists (
        select 1 from {{ source('raw_musicbrainz', 'albums') }} as a
        where a.band_name = x.band
          and {{ normalize_title('a.title') }} = {{ normalize_title('x.album_title') }}
    )
