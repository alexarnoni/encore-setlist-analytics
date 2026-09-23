-- gaps_count is never negative, and returned_after_abandonment is exactly
-- "at least one intermediate gap" (gaps_count > 0).
-- Returns violating rows; passes when it returns none. Tagged `survival`.
{{ config(tags=['survival']) }}

select
    band,
    song_title,
    gaps_count,
    returned_after_abandonment
from {{ source('encore_survival', 'mart_song_survival') }}
where gaps_count < 0
   or returned_after_abandonment <> (gaps_count > 0)
