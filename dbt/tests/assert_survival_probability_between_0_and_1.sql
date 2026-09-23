-- Every survival probability is a share, so it must lie in [0, 1]
-- (spec-03 requirement 11). Tagged `survival`: only meaningful after the
-- `analyze` task has written the marts (see dbt/README.md).
-- Returns violating rows; passes when it returns none.
{{ config(tags=['survival']) }}

select
    band,
    album,
    n_window,
    t_shows,
    survival_probability
from {{ source('encore_survival', 'mart_survival_curves') }}
where survival_probability < 0 or survival_probability > 1
