-- Arithmetic and scope that must hold inside mart_tour_rotation (spec-03 T4):
--   * rotation = 1 - mean_jaccard, both in [0, 1];
--   * pairs = shows - 1 (a chain of consecutive shows);
--   * shows >= 5 (tours below that are excluded, never appear here);
--   * core_songs <= distinct_songs;
--   * 'Unknown tour' never appears (it cannot be measured: no real pairs);
--   * first_year <= last_year.
-- Returns violating rows; passes when it returns none.
select
    band,
    tour_name,
    shows,
    pairs,
    mean_jaccard,
    rotation,
    core_songs,
    distinct_songs,
    first_year,
    last_year
from {{ ref('mart_tour_rotation') }}
where abs(rotation - (1 - mean_jaccard)) > 0.0001
   or rotation < 0 or rotation > 1
   or mean_jaccard < 0 or mean_jaccard > 1
   or pairs <> shows - 1
   or shows < 5
   or core_songs > distinct_songs
   or tour_name = 'Unknown tour'
   or first_year > last_year
