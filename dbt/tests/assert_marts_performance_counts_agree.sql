-- The two marts are built from the same performances, so for every
-- (band, year) they must agree on how many performances there were and how
-- many matched — mart_repertoire_age just splits them by tour
-- (spec-02a item 15). A disagreement means one mart's filter or
-- aggregation drifted from the other's. Passes when it returns no rows.
with age_mart as (

    select
        band,
        show_year,
        sum(performances) as performances,
        sum(matched_performances) as matched_performances
    from {{ ref('mart_repertoire_age') }}
    group by band, show_year

)

select
    coalesce(a.band, q.band) as band,
    coalesce(a.show_year, q.show_year) as show_year,
    a.performances as age_mart_performances,
    q.performances as quality_mart_performances,
    a.matched_performances as age_mart_matched,
    q.matched_performances as quality_mart_matched
from age_mart as a
full outer join {{ ref('mart_match_quality') }} as q
    on q.band = a.band and q.show_year = a.show_year
where a.performances is distinct from q.performances
   or a.matched_performances is distinct from q.matched_performances
