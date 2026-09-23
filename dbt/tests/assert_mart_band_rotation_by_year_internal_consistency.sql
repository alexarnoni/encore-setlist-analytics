-- rotation = 1 - mean_jaccard, both in [0, 1] (spec-03 T5).
-- Returns violating rows; passes when it returns none.
select
    band,
    show_year,
    pairs,
    mean_jaccard,
    rotation
from {{ ref('mart_band_rotation_by_year') }}
where abs(rotation - (1 - mean_jaccard)) > 0.0001
   or rotation < 0 or rotation > 1
   or mean_jaccard < 0 or mean_jaccard > 1
   or pairs < 1
