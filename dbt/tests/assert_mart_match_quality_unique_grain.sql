-- mart_match_quality's grain is (band, show_year): one row each
-- (spec-02a item 15). Composite key -> singular test. Passes when it
-- returns no rows.
select
    band,
    show_year,
    count(*) as n
from {{ ref('mart_match_quality') }}
group by band, show_year
having count(*) > 1
