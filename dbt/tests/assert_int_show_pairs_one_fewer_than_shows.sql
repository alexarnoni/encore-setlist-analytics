-- In every band and tour with n shows there are exactly n - 1 consecutive
-- pairs, and each show is the first of at most one pair and the second of at
-- most one (a chain, not a web). Counted from int_show_song_sets directly, not
-- from the pairs model. Passes when it returns no rows.
with shows as (

    select band, tour_name, count(distinct show_key) as shows
    from {{ ref('int_show_song_sets') }}
    where tour_name <> 'Unknown tour'
    group by band, tour_name

),

pairs as (

    select
        band,
        tour_name,
        count(*) as pairs,
        count(distinct first_show_key) as firsts,
        count(distinct second_show_key) as seconds
    from {{ ref('int_show_pairs') }}
    group by band, tour_name

)

select
    s.band,
    s.tour_name,
    s.shows,
    coalesce(p.pairs, 0) as pairs
from shows as s
left join pairs as p
    on p.band = s.band and p.tour_name = s.tour_name
where coalesce(p.pairs, 0) <> s.shows - 1
   or coalesce(p.firsts, 0) <> coalesce(p.pairs, 0)
   or coalesce(p.seconds, 0) <> coalesce(p.pairs, 0)
