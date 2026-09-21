-- Arithmetic that must hold inside mart_match_quality (spec-02a item 15):
-- you cannot match more than you played, whether counting plays or titles,
-- a title needs at least one play, and album-backed matches are a subset of
-- all matches (match_rate_by_album <= match_rate_by_performance).
-- Returns violating rows; passes when it returns none.
select
    band,
    show_year,
    performances,
    matched_performances,
    distinct_songs,
    distinct_songs_matched,
    match_rate_by_performance,
    match_rate_by_album
from {{ ref('mart_match_quality') }}
where matched_performances > performances
   or distinct_songs_matched > distinct_songs
   or distinct_songs > performances
   or match_rate_by_album > match_rate_by_performance
