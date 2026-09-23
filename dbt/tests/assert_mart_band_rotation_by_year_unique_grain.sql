-- mart_band_rotation_by_year's grain is (band, show_year): one row each.
-- Passes when it returns no rows.
select
    band,
    show_year,
    count(*) as n
from {{ ref('mart_band_rotation_by_year') }}
group by band, show_year
having count(*) > 1
