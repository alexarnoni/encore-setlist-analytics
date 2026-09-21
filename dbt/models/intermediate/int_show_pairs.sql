-- Consecutive pairs of shows (same band and tour, adjacent in date order) with
-- their Jaccard similarity (spec-03 R2). All the logic is in the macro
-- consecutive_show_pairs, which the fixture test test_jaccard_cases also runs
-- on literal sets with known answers.
--
-- A view over EPHEMERAL setlist.fm data (it carries show keys and dates): fine
-- in `intermediate`, never in `analytics`.
{{ consecutive_show_pairs(ref('int_show_song_sets')) }}
