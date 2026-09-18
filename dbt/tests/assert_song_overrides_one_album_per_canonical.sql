-- Several raw setlist names may map to one canonical song, but they must
-- agree on its album — otherwise which album/year the catalog row gets
-- would depend on row order (spec-02a item 12; int_song_catalog picks
-- deterministically, but a contradiction in the seed is a mistake to
-- surface, not to paper over). Passes when it returns no rows.
select
    band,
    {{ normalize_title('canonical_song_title') }} as canonical_normalized,
    count(distinct {{ normalize_title('album_title') }}) as distinct_albums
from {{ ref('seed_song_overrides') }}
where nullif(btrim(album_title), '') is not null
group by band, {{ normalize_title('canonical_song_title') }}
having count(distinct {{ normalize_title('album_title') }}) > 1
