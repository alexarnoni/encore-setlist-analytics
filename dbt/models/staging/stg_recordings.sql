-- Recordings from raw_musicbrainz.recordings, deduplicated by normalized
-- title per band, keeping the EARLIEST release (spec-02a R2.4).
--
-- Why: MusicBrainz has one recording row per release of a song, so
-- "Live Forever" appears ~200 times (singles, compilations, reissues,
-- live versions...). What matters downstream is the song's first
-- release year, so collapse to one row per (band, title_normalized).
--
-- "Earliest" orders by release_year (an int; NULL last) and only then by
-- the raw date text, rather than sorting the text alone: MusicBrainz
-- dates are mixed precision ("1995", "1995-10", "1995-10-02") and text
-- ordering of anything unparseable is meaningless. recording_mbid is the
-- last tie-break so the result is deterministic between runs.
--
-- A row whose title normalizes to '' (all punctuation) can't be matched
-- to anything, so it is dropped rather than collapsed into one bucket.

with recordings as (

    select * from {{ source('raw_musicbrainz', 'recordings') }}

),

normalized as (

    select
        recording_mbid,
        band_name as band,
        title,
        {{ normalize_title('title') }} as title_normalized,
        nullif(btrim(first_release_date), '') as first_release_date,
        {{ release_year("nullif(btrim(first_release_date), '')") }} as release_year
    from recordings

),

ranked as (

    select
        *,
        row_number() over (
            partition by band, title_normalized
            order by release_year asc nulls last,
                     first_release_date asc nulls last,
                     recording_mbid
        ) as rn
    from normalized
    where title_normalized <> ''

)

select
    band,
    recording_mbid,
    title,
    title_normalized,
    first_release_date,
    release_year
from ranked
where rn = 1
