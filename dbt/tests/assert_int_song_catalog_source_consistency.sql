-- catalog_source and reference_album must agree (spec-02a item 12):
--   'album'     -> always has a reference album (it IS a track on one)
--   'recording' -> never has one (it is here precisely because no album has it)
-- ('override' may legitimately carry an album title that stg_albums does
--  not know; that case is caught by assert_song_override_albums_exist.)
-- Passes when it returns no rows.
select
    band,
    title_normalized,
    catalog_source,
    reference_album
from {{ ref('int_song_catalog') }}
where (catalog_source = 'album' and reference_album is null)
   or (catalog_source = 'recording' and reference_album is not null)
