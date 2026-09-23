-- mart_tour_rotation's grain is (band, tour_name): one row each.
-- Passes when it returns no rows.
select
    band,
    tour_name,
    count(*) as n
from {{ ref('mart_tour_rotation') }}
group by band, tour_name
having count(*) > 1
