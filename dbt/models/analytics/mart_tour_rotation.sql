-- How much a band's setlist changes between shows of the same tour
-- (spec-03 R2/R3). Grain: band, tour_name.
--
-- * Rotation = 1 - mean Jaccard similarity over the tour's consecutive pairs
--   (int_show_pairs already excludes 'Unknown tour' and non-adjacent shows).
-- * 'Unknown tour' itself never gets a row here: it has no real pairs (a
--   pooled bucket of unrelated shows, same reasoning as mart_repertoire_age's
--   'Unknown tour' label, but here it cannot be measured at all).
-- * Tours with fewer than MIN_TOUR_SHOWS (5) shows are excluded (spec text).
--   Since every tour with >= 1 show would otherwise have >= 0 pairs, this is
--   the only size filter needed.
-- * Core song = present in at least 90% of the tour's shows, computed as an
--   exact fraction (shows_with_song * 10 >= shows * 9) to avoid float
--   rounding at the boundary.
--
-- No show key, date, venue or raw title (R5): only first_year/last_year survive.
{% set min_tour_shows = 5 %}

with show_sets as (

    select band, tour_name, show_key, show_date, song_key
    from {{ ref('int_show_song_sets') }}
    where tour_name <> 'Unknown tour'

),

shows as (

    select
        band,
        tour_name,
        show_key,
        show_date,
        count(*) as set_size
    from show_sets
    group by band, tour_name, show_key, show_date

),

tours as (

    select
        band,
        tour_name,
        count(*) as shows,
        min(extract(year from show_date))::int as first_year,
        max(extract(year from show_date))::int as last_year,
        (percentile_cont(0.5) within group (order by set_size))::numeric as median_setlist_size
    from shows
    group by band, tour_name

),

pairs as (

    select
        band,
        tour_name,
        count(*) as pairs,
        avg(jaccard) as mean_jaccard
    from {{ ref('int_show_pairs') }}
    group by band, tour_name

),

song_stats as (

    select
        band,
        tour_name,
        song_key,
        count(distinct show_key) as shows_with_song
    from show_sets
    group by band, tour_name, song_key

),

song_totals as (

    select
        ss.band,
        ss.tour_name,
        count(*) as distinct_songs,
        count(*) filter (where ss.shows_with_song * 10 >= t.shows * 9) as core_songs
    from song_stats as ss
    inner join tours as t
        on t.band = ss.band and t.tour_name = ss.tour_name
    group by ss.band, ss.tour_name

)

select
    t.band,
    t.tour_name,
    t.first_year,
    t.last_year,
    t.shows,
    p.pairs,
    round(p.mean_jaccard::numeric, 4) as mean_jaccard,
    round((1 - p.mean_jaccard)::numeric, 4) as rotation,
    round(t.median_setlist_size, 4) as median_setlist_size,
    s.core_songs,
    s.distinct_songs,
    current_timestamp as computed_at
from tours as t
inner join pairs as p
    on p.band = t.band and p.tour_name = t.tour_name
inner join song_totals as s
    on s.band = t.band and s.tour_name = t.tour_name
where t.shows >= {{ min_tour_shows }}
