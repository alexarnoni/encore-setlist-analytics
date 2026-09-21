-- match_rate_by_album re-derived from int_performances with a different
-- expression than the mart uses: a performance is album-backed when it is
-- matched AND its catalog source is not the recording-only one. That must
-- agree with the mart's `reference_album is not null` count for every
-- band/year; a drift in either shows up here. Passes when it returns no rows.
with expected as (

    select
        band,
        show_year,
        round(
            count(*) filter (where is_matched and catalog_source <> 'recording')::numeric
            / count(*),
            4
        ) as expected_rate
    from {{ ref('int_performances') }}
    where show_year is not null
    group by band, show_year

)

select
    q.band,
    q.show_year,
    q.match_rate_by_album,
    e.expected_rate
from {{ ref('mart_match_quality') }} as q
full outer join expected as e
    on e.band = q.band and e.show_year = q.show_year
where q.match_rate_by_album is distinct from e.expected_rate
