-- At most one distinct first_release_year per (band, canonical song):
-- two different fixes for the same song would be ambiguous.
-- Passes when it returns no rows.
select
    band,
    {{ normalize_title('canonical_song_title') }} as canonical_normalized,
    count(distinct first_release_year) as distinct_years
from {{ ref('seed_song_overrides') }}
where nullif(btrim(first_release_year), '') is not null
group by band, {{ normalize_title('canonical_song_title') }}
having count(distinct first_release_year) > 1
