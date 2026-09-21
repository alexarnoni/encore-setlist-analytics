-- release_year must follow the "first official release year" rule
-- (product.md): a seed fix wins; otherwise it is the earlier of the album
-- year and the recording year, ignoring a missing side. Recomputed here
-- with explicit CASE logic instead of `least`, so the test is not just the
-- model's own expression. Passes when it returns no rows.
select
    band,
    title_normalized,
    release_year,
    album_year,
    recording_year,
    release_year_fixed
from {{ ref('int_song_catalog') }}
where not release_year_fixed
  and release_year is distinct from (
        case
            when album_year is null then recording_year
            when recording_year is null then album_year
            when album_year <= recording_year then album_year
            else recording_year
        end
    )
