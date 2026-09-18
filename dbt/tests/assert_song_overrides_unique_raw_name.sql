-- A raw setlist name may map to only ONE canonical song per band; two rows
-- sending the same raw name to different canonicals make the result depend
-- on row order (spec-02a item 13). Contradictions in the seed are surfaced,
-- not silently resolved. Passes when it returns no rows.
select
    band,
    {{ normalize_title('raw_song_name') }} as raw_normalized,
    count(distinct {{ normalize_title('canonical_song_title') }}) as distinct_canonicals
from {{ ref('seed_song_overrides') }}
where nullif(btrim(raw_song_name), '') is not null
group by band, {{ normalize_title('raw_song_name') }}
having count(distinct {{ normalize_title('canonical_song_title') }}) > 1
