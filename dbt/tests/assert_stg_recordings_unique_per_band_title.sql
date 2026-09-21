-- stg_recordings must hold exactly one row per (band, title_normalized)
-- (spec-02a item 10). Composite uniqueness can't be expressed with the
-- built-in `unique` test (single column only, no dbt_utils here), hence
-- a singular test. Passes when it returns no rows.
select
    band,
    title_normalized,
    count(*) as n
from {{ ref('stg_recordings') }}
group by band, title_normalized
having count(*) > 1
