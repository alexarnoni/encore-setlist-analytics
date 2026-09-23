-- The two rotation marts are built from the same qualifying pairs, so for
-- every band the sum of pairs over the yearly mart must equal the sum over
-- the tour mart (mart_band_rotation_by_year just splits them by year instead
-- of by tour). A full outer join, so a band missing from either fails too.
-- Passes when it returns no rows.
with by_tour as (

    select band, sum(pairs) as pairs
    from {{ ref('mart_tour_rotation') }}
    group by band

),

by_year as (

    select band, sum(pairs) as pairs
    from {{ ref('mart_band_rotation_by_year') }}
    group by band

)

select
    coalesce(t.band, y.band) as band,
    t.pairs as tour_mart_pairs,
    y.pairs as year_mart_pairs
from by_tour as t
full outer join by_year as y on y.band = t.band
where t.pairs is distinct from y.pairs
