-- Every match rate is a share, so it must lie in [0, 1] (spec-02a R7.4).
-- Covers all four rate columns in both marts. NULL is allowed for
-- match_rate_by_title (no usable title in the cell): comparisons with NULL
-- are not true, so it never flags — the not_null tests own the columns
-- that may not be empty. Returns violating rows; passes when it returns none.
select
    'mart_repertoire_age' as model,
    'match_rate' as rate_column,
    band,
    show_year,
    match_rate as rate
from {{ ref('mart_repertoire_age') }}
where match_rate < 0 or match_rate > 1

union all

select
    'mart_match_quality',
    'match_rate_by_performance',
    band,
    show_year,
    match_rate_by_performance
from {{ ref('mart_match_quality') }}
where match_rate_by_performance < 0 or match_rate_by_performance > 1

union all

select
    'mart_match_quality',
    'match_rate_by_title',
    band,
    show_year,
    match_rate_by_title
from {{ ref('mart_match_quality') }}
where match_rate_by_title < 0 or match_rate_by_title > 1

union all

select
    'mart_match_quality',
    'match_rate_by_album',
    band,
    show_year,
    match_rate_by_album
from {{ ref('mart_match_quality') }}
where match_rate_by_album < 0 or match_rate_by_album > 1
