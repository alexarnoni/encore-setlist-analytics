-- Reconciliation of the analytics marts against their source, per band.
-- Raw setlist.fm data is deleted at the end of every run, so this is the
-- only chance to prove, inside the run, that no performance was lost or
-- invented on the way to the marts: for every band, the performances in
-- mart_repertoire_age and in mart_match_quality (and their matched counts)
-- must equal what int_performances holds. mart_repertoire_age's
-- aged_performances (matched performances with a release year) is
-- reconciled too: the consistency test cannot catch it counting all matched
-- performances, because aged <= matched would still hold.
--
-- "What int_performances holds" = its rows with a known show_year. Both
-- marts leave out performances that cannot be placed in a year, by design
-- (see their headers); assert_no_undated_performances_left_out_of_marts
-- reports how many that is, so nothing is dropped silently.
--
-- A band missing from a mart, or present only in a mart, also fails
-- (the bands list is the union of all three). Passes when it returns no rows.
with source as (

    select
        band,
        count(*) as performances,
        count(*) filter (where is_matched) as matched_performances,
        count(*) filter (where is_matched and release_year is not null) as aged_performances
    from {{ ref('int_performances') }}
    where show_year is not null
    group by band

),

age_mart as (

    select
        band,
        sum(performances) as performances,
        sum(matched_performances) as matched_performances,
        sum(aged_performances) as aged_performances
    from {{ ref('mart_repertoire_age') }}
    group by band

),

quality_mart as (

    select
        band,
        sum(performances) as performances,
        sum(matched_performances) as matched_performances
    from {{ ref('mart_match_quality') }}
    group by band

),

bands as (

    select band from source
    union
    select band from age_mart
    union
    select band from quality_mart

)

select
    b.band,
    s.performances as int_performances,
    a.performances as age_mart_performances,
    q.performances as quality_mart_performances,
    s.matched_performances as int_matched,
    a.matched_performances as age_mart_matched,
    q.matched_performances as quality_mart_matched,
    s.aged_performances as int_aged,
    a.aged_performances as age_mart_aged
from bands as b
left join source as s on s.band = b.band
left join age_mart as a on a.band = b.band
left join quality_mart as q on q.band = b.band
where s.performances is distinct from a.performances
   or s.performances is distinct from q.performances
   or s.matched_performances is distinct from a.matched_performances
   or s.matched_performances is distinct from q.matched_performances
   or s.aged_performances is distinct from a.aged_performances
