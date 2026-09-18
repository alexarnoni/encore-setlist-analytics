-- One row per performed song, from raw_setlistfm.setlist_entries
-- (spec-02a R2.2). Medleys ("A / B") are split into one row per song,
-- each keeping the ORIGINAL entry's position and set_index — the spec
-- says "keeping the original position", it does not say how sibling
-- rows are told apart, so `medley_part` (1, 2, ...) is added: with it
-- (setlist_id, set_index, position, medley_part) is a unique key.
--
-- Flags are inherited by every part of a medley: is_tape / is_cover /
-- is_encore describe the entry as setlist.fm recorded it, and setlist.fm
-- has no per-song flags inside a medley.
--
-- Entries with an empty/blank name produce no rows (split_medley yields
-- nothing for them) — they are not identifiable songs.

with entries as (

    select * from {{ source('raw_setlistfm', 'setlist_entries') }}

),

setlists as (

    select setlist_id, band_name from {{ source('raw_setlistfm', 'setlists') }}

)

select
    e.setlist_id,
    s.band_name as band,
    p.part as song_name_raw,
    e.position,
    e.set_idx as set_index,
    e.is_encore,
    e.is_cover,
    e.is_tape,
    p.part_count > 1 as is_medley,
    p.part_idx::int as medley_part
from entries as e
inner join setlists as s on s.setlist_id = e.setlist_id
cross join lateral {{ split_medley('e.song_name') }} as p
