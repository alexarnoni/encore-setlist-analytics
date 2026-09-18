-- The mart's grain is (band, tour_name, show_year): one row each
-- (spec-02a item 14). A composite key -> singular test. Passes when it
-- returns no rows.
select
    band,
    tour_name,
    show_year,
    count(*) as n
from {{ ref('mart_repertoire_age') }}
group by band, tour_name, show_year
having count(*) > 1
