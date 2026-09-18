-- Arithmetic that must hold inside mart_match_quality (spec-02a item 15):
-- you cannot match more than you played, whether counting plays or titles,
-- and a title needs at least one play. Returns violating rows; passes when
-- it returns none.
select
    band,
    show_year,
    performances,
    matched_performances,
    distinct_songs,
    distinct_songs_matched
from {{ ref('mart_match_quality') }}
where matched_performances > performances
   or distinct_songs_matched > distinct_songs
   or distinct_songs > performances
