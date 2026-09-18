-- (setlist_id, set_index, position, medley_part) must identify exactly one
-- row of stg_setlist_entries (spec-02a item 11). A composite key can't be
-- checked with the built-in `unique` (single column, no dbt_utils), hence
-- a singular test. This was only checked ad hoc when the model was built
-- (item 8); this makes it a permanent guard. Passes when it returns no rows.
select
    setlist_id,
    set_index,
    position,
    medley_part,
    count(*) as n
from {{ ref('stg_setlist_entries') }}
group by setlist_id, set_index, position, medley_part
having count(*) > 1
