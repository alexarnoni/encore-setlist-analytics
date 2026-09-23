-- Reconciliation (spec-03 requirement 15): the number of eligible songs a
-- band has in mart_song_survival must equal the number of eligible songs
-- independently re-derived here, in SQL, from int_performances and
-- int_song_catalog (the same rule as encore.analysis.survival.is_eligible,
-- written a second time rather than reused, so drift in either implementation
-- shows up here). Eligible = at least 3 matched, dated performances, and
-- matched to a studio album or to a recording that has a release year.
-- Tagged `survival`. A full outer join, so a band missing from either side
-- fails too. Returns violating rows; passes when it returns none.
{{ config(tags=['survival']) }}

-- `materialized`: filtering int_performances directly (a view) makes
-- Postgres re-evaluate it per output row instead of once — over 4 minutes at
-- production scale for a similar query (see int_show_song_sets). Compute it
-- once here, then filter.
with all_performances as materialized (

    select band, title_normalized, is_matched, show_year
    from {{ ref('int_performances') }}

),

performances as (

    select
        band,
        title_normalized,
        count(*) as n
    from all_performances
    where is_matched and show_year is not null
    group by band, title_normalized

),

eligible as (

    select p.band, p.title_normalized
    from performances as p
    inner join {{ ref('int_song_catalog') }} as c
        on c.band = p.band and c.title_normalized = p.title_normalized
    where p.n >= 3
      and (c.reference_album is not null or c.release_year is not null)

),

expected as (

    select band, count(*) as songs
    from eligible
    group by band

),

actual as (

    select band, count(*) as songs
    from {{ source('encore_survival', 'mart_song_survival') }}
    group by band

)

select
    coalesce(e.band, a.band) as band,
    e.songs as expected_songs,
    a.songs as actual_songs
from expected as e
full outer join actual as a on a.band = e.band
where e.songs is distinct from a.songs
