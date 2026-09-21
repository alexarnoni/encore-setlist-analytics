{#-
  Consecutive show pairs of a band and tour, with their Jaccard similarity
  (spec-03 R2). Takes any relation (or parenthesised subquery with an alias)
  that has show_key, band, tour_name, show_date and song_key, one row per show
  and song. The model int_show_pairs applies it to int_show_song_sets; the
  fixture test applies it to literal sets with known answers.

  * A pair is two shows of the same band and tour that are adjacent in
    (show_date, show_key) order; ties on the date are broken by show_key so the
    order is deterministic.
  * Shows of the tour 'Unknown tour' are never paired.
  * Jaccard = |A intersect B| / |A union B|; both sets are non-empty by
    construction (a show only exists if it has a matched song), so the union is
    never 0.
  * `materialized` on the sets: they are read several times below, and a view
    behind them must be evaluated once (see int_show_song_sets for why
    evaluation order matters at production size).
-#}
{% macro consecutive_show_pairs(show_song_sets) %}
with sets as materialized (

    select show_key, band, tour_name, show_date, song_key
    from {{ show_song_sets }}
    where tour_name <> 'Unknown tour'

),

shows as (

    select
        show_key,
        band,
        tour_name,
        show_date,
        count(*) as set_size,
        row_number() over (
            partition by band, tour_name
            order by show_date, show_key
        ) as show_order
    from sets
    group by show_key, band, tour_name, show_date

),

pairs as (

    select
        a.band,
        a.tour_name,
        a.show_key as first_show_key,
        b.show_key as second_show_key,
        a.show_date as first_show_date,
        b.show_date as second_show_date,
        a.set_size as first_set_size,
        b.set_size as second_set_size
    from shows as a
    inner join shows as b
        on b.band = a.band
       and b.tour_name = a.tour_name
       and b.show_order = a.show_order + 1

),

overlap as (

    select
        p.first_show_key,
        p.second_show_key,
        count(*) as intersection_size
    from pairs as p
    inner join sets as sa on sa.show_key = p.first_show_key
    inner join sets as sb
        on sb.show_key = p.second_show_key
       and sb.song_key = sa.song_key
    group by p.first_show_key, p.second_show_key

)

select
    p.band,
    p.tour_name,
    p.first_show_key,
    p.second_show_key,
    p.first_show_date,
    p.second_show_date,
    p.first_set_size,
    p.second_set_size,
    coalesce(o.intersection_size, 0) as intersection_size,
    p.first_set_size + p.second_set_size - coalesce(o.intersection_size, 0) as union_size,
    coalesce(o.intersection_size, 0)::numeric
        / (p.first_set_size + p.second_set_size - coalesce(o.intersection_size, 0)) as jaccard
from pairs as p
left join overlap as o
    on o.first_show_key = p.first_show_key
   and o.second_show_key = p.second_show_key
{% endmacro %}
