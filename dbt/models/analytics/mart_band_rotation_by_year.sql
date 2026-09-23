-- Rotation by band and year, weighted by pairs (spec-03 R4). Grain: band,
-- show_year.
--
-- A pair belongs to the year of its SECOND show (decision Q3,
-- spec-03-progress.md section 4a). Only pairs from tours that qualify for
-- mart_tour_rotation are counted: joining against it (rather than
-- re-filtering int_show_pairs) makes the two marts agree by construction —
-- a tour excluded there (fewer than 5 shows) is excluded here too, and
-- 'Unknown tour' pairs never exist in int_show_pairs in the first place.
--
-- "Weighted by pairs" = every pair counts once in the mean, regardless of
-- which tour or how long that tour is; a year that had one 40-show tour and
-- one 5-show tour is dominated by the first tour's pairs, not averaged
-- tour-by-tour.
with qualifying_pairs as (

    select
        p.band,
        extract(year from p.second_show_date)::int as show_year,
        p.jaccard
    from {{ ref('int_show_pairs') }} as p
    inner join {{ ref('mart_tour_rotation') }} as t
        on t.band = p.band and t.tour_name = p.tour_name

)

select
    band,
    show_year,
    count(*) as pairs,
    round(avg(jaccard)::numeric, 4) as mean_jaccard,
    round((1 - avg(jaccard))::numeric, 4) as rotation,
    current_timestamp as computed_at
from qualifying_pairs
group by band, show_year
