-- WARN-level companion to assert_marts_reconcile_with_int_performances.
-- The marts drop performances whose show has no usable date (show_year is
-- NULL): they cannot be placed in a year. This lists, per band, how many
-- performances that is, so the reconciliation test can compare against the
-- dated ones without hiding the rest. A warning means "look at the
-- setlist dates for this band", not a pipeline failure.
{{ config(severity='warn') }}

select
    band,
    count(*) as undated_performances
from {{ ref('int_performances') }}
where show_year is null
group by band
