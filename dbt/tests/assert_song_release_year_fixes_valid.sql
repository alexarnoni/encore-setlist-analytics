-- A first_release_year in seed_song_overrides must be a plausible year
-- (1900-2099), and its row must name the song (band + canonical title); otherwise
-- the model silently ignores it. Passes when it returns no rows.
select
    band,
    canonical_song_title,
    first_release_year
from {{ ref('seed_song_overrides') }}
where nullif(btrim(first_release_year), '') is not null
  and (
        first_release_year !~ '^(19|20)[0-9]{2}$'
        or nullif(btrim(band), '') is null
        or nullif(btrim(canonical_song_title), '') is null
      )
