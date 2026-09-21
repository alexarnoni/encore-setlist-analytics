-- (setlist_id, set_index, position, medley_part) identifies exactly one
-- performance (spec-02a item 13). The catalog join is on a unique key, so a
-- duplicate here would mean the join fanned out and every downstream count
-- is inflated. Passes when it returns no rows.
select
    setlist_id,
    set_index,
    position,
    medley_part,
    count(*) as n
from {{ ref('int_performances') }}
group by setlist_id, set_index, position, medley_part
having count(*) > 1
