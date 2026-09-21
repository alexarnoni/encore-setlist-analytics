-- Average repertoire age (spec-02a R5). Grain: band, tour, year.
-- PERSISTENT aggregate table — the only thing in this project that
-- survives the pipeline run's cleanup of raw_setlistfm, so it must
-- contain aggregated numbers only: no setlist id, show date, venue or
-- song title (enforced by a singular test, R7.2).
--
-- Rules
-- * A performance's repertoire age is show_year - release_year (the song's
--   first official release year, product.md), and a
--   NEGATIVE age (the song was played before its release year, i.e. new
--   material at that show) is clamped to 0. Decision recorded in
--   spec-02a-progress.md item 13/14: the KPI asks whether a band bets on
--   new material, so an unreleased song counts as age 0 rather than being
--   dropped or going negative (R7.3 forbids a negative average).
-- * Only matched performances with a known age enter the average /
--   median / oldest / newest. Tape and cover entries never reach this
--   model (int_performances excludes them).
-- * `performances` and `matched_performances` count every non-tape,
--   non-cover performance in the cell, so match_rate is honest about
--   what did not resolve to the catalog.
-- * A show with no tour name is grouped under 'Unknown tour' (tour
--   inference is out of scope for this slice).
-- * Performances whose show_year is unknown (an unparseable source date)
--   cannot be placed in a year and are left out; a warn-level test on
--   stg_setlists.show_year surfaces those.
-- * `shows` = distinct shows with at least one performance in the cell.

with performances as (

    select
        band,
        coalesce(tour_name, 'Unknown tour') as tour_name,
        show_year,
        setlist_id,
        is_matched,
        release_year,
        -- CASE, not greatest(): greatest() ignores NULLs, so
        -- greatest(NULL, 0) would turn "no age" into "age 0".
        case when repertoire_age < 0 then 0 else repertoire_age end as age
    from {{ ref('int_performances') }}
    where show_year is not null

)

select
    band,
    tour_name,
    show_year,
    count(distinct setlist_id) as shows,
    count(*) as performances,
    count(*) filter (where is_matched) as matched_performances,
    round(count(*) filter (where is_matched)::numeric / count(*), 4) as match_rate,
    round((avg(age) filter (where is_matched and age is not null))::numeric, 4)
        as avg_repertoire_age,
    round(
        (percentile_cont(0.5) within group (order by age)
            filter (where is_matched and age is not null))::numeric, 4
    ) as median_repertoire_age,
    min(release_year) filter (where is_matched and age is not null) as oldest_song_year,
    max(release_year) filter (where is_matched and age is not null) as newest_song_year,
    current_timestamp as computed_at
from performances
group by band, tour_name, show_year
