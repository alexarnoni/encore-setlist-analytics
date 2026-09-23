-- A Kaplan-Meier curve never goes back up: within one (band, album, n_window)
-- curve, survival_probability at a later t_shows can only stay the same or
-- drop (spec-03 requirement 11). Tagged `survival`.
-- Returns violating rows; passes when it returns none.
{{ config(tags=['survival']) }}

with ordered as (

    select
        band,
        album,
        n_window,
        t_shows,
        survival_probability,
        lag(survival_probability) over (
            partition by band, album, n_window
            order by t_shows
        ) as previous_probability
    from {{ source('encore_survival', 'mart_survival_curves') }}

)

select
    band,
    album,
    n_window,
    t_shows,
    previous_probability,
    survival_probability
from ordered
where previous_probability is not null
  and survival_probability > previous_probability + 0.0000001
