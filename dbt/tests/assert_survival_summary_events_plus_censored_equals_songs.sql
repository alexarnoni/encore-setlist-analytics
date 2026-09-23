-- events + censored = songs for every (band, album, n_window)
-- (spec-03 requirement 11). Tagged `survival`.
-- Returns violating rows; passes when it returns none.
{{ config(tags=['survival']) }}

select
    band,
    album,
    n_window,
    songs,
    events,
    censored
from {{ source('encore_survival', 'mart_survival_summary') }}
where events + censored <> songs
