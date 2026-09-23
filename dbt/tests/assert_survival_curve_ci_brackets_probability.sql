-- Not in the spec's own wording, but the same kind of guard: a confidence
-- interval must actually contain the point estimate, and stay in [0, 1]
-- itself. Tagged `survival`. Returns violating rows; passes when it returns
-- none.
{{ config(tags=['survival']) }}

select
    band,
    album,
    n_window,
    t_shows,
    ci_lower,
    survival_probability,
    ci_upper
from {{ source('encore_survival', 'mart_survival_curves') }}
where ci_lower > survival_probability
   or survival_probability > ci_upper
   or ci_lower < 0
   or ci_upper > 1
