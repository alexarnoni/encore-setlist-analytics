-- A band cannot have a negative average repertoire age (spec-02a R7.3).
-- A song played before its release year would give a negative age; the mart
-- clamps those to 0, and this test proves the clamp holds. The median comes
-- from the same clamped ages, so it is checked too. NULL (no dated matched
-- performance in the cell) is allowed: `< 0` is not true for NULL, which is
-- intended. Returns violating rows; passes when it returns none.
select
    band,
    tour_name,
    show_year,
    avg_repertoire_age,
    median_repertoire_age
from {{ ref('mart_repertoire_age') }}
where avg_repertoire_age < 0
   or median_repertoire_age < 0
