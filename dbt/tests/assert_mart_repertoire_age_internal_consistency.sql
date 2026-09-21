-- Arithmetic that must hold inside mart_repertoire_age:
--   * aged_performances <= matched_performances <= performances (you cannot
--     age more plays than matched, nor match more than were played);
--   * the average, median and oldest/newest year exist exactly when at least
--     one performance was aged: NULL when aged_performances = 0, never NULL
--     otherwise (they are all computed over the same aged rows).
-- Returns violating rows; passes when it returns none.
select
    band,
    tour_name,
    show_year,
    performances,
    matched_performances,
    aged_performances,
    avg_repertoire_age,
    median_repertoire_age,
    oldest_song_year,
    newest_song_year
from {{ ref('mart_repertoire_age') }}
where aged_performances > matched_performances
   or matched_performances > performances
   or aged_performances < 0
   or (aged_performances = 0 and (
          avg_repertoire_age is not null
       or median_repertoire_age is not null
       or oldest_song_year is not null
       or newest_song_year is not null))
   or (aged_performances > 0 and (
          avg_repertoire_age is null
       or median_repertoire_age is null
       or oldest_song_year is null
       or newest_song_year is null))
