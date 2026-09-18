-- How well setlist songs resolve to the song catalog (spec-02a R6).
-- Grain: band, year. PERSISTENT aggregate table: counts and rates only —
-- no setlist id, show date, venue or song title.
--
-- Two views of the same question:
-- * by PERFORMANCE (match_rate_by_performance): weighted by plays, so a
--   song played 600 times counts 600 times. This is the primary metric
--   (product.md: "% of performances, weighted by plays") — it says how
--   much of what the audience actually heard is covered.
-- * by TITLE (match_rate_by_title): every distinct song counts once. It
--   is the harsher view: unmatched rarities weigh as much as hits.
--
-- "Matched" = the performance resolved to the catalog (album, recording
-- or override) — the same is_matched flag mart_repertoire_age uses, so the
-- two marts agree on counts (assert_marts_performance_counts_agree).
--
-- distinct_songs counts distinct title_normalized — the key actually used
-- to join the catalog, so two raw names an override maps to one canonical
-- song count once. A key that normalizes to '' is not a title and is not
-- counted (it still counts as an unmatched performance).
--
-- Performances with an unknown show_year cannot be placed in a year and
-- are left out, as in mart_repertoire_age.

with performances as (

    select
        band,
        show_year,
        title_normalized,
        is_matched
    from {{ ref('int_performances') }}
    where show_year is not null

)

select
    band,
    show_year,
    count(*) as performances,
    count(*) filter (where is_matched) as matched_performances,
    round(count(*) filter (where is_matched)::numeric / count(*), 4)
        as match_rate_by_performance,
    count(distinct title_normalized) filter (where title_normalized <> '')
        as distinct_songs,
    count(distinct title_normalized) filter (where title_normalized <> '' and is_matched)
        as distinct_songs_matched,
    round(
        count(distinct title_normalized) filter (where title_normalized <> '' and is_matched)::numeric
        / nullif(count(distinct title_normalized) filter (where title_normalized <> ''), 0),
        4
    ) as match_rate_by_title,
    current_timestamp as computed_at
from performances
group by band, show_year
