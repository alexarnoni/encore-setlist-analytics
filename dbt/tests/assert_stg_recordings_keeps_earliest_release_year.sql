-- The row stg_recordings keeps for each (band, title_normalized) must
-- carry the EARLIEST release year among all raw recordings that
-- normalize to that title (spec-02a item 10).
--
-- Recomputed here with a plain min() aggregate straight over the raw
-- table, deliberately NOT reusing the window function in the model, so
-- this is an independent check of it. min() ignores NULLs, which matches
-- the model's "NULL years last": a title with any dated recording must
-- keep a dated row; a title with none keeps NULL. Passes when it returns
-- no rows.
with raw_normalized as (

    select
        band_name as band,
        {{ normalize_title('title') }} as title_normalized,
        {{ release_year("nullif(btrim(first_release_date), '')") }} as release_year
    from {{ source('raw_musicbrainz', 'recordings') }}

),

expected as (

    select band, title_normalized, min(release_year) as earliest_year
    from raw_normalized
    where title_normalized <> ''
    group by band, title_normalized

)

select
    s.band,
    s.title_normalized,
    s.release_year as kept_year,
    e.earliest_year
from {{ ref('stg_recordings') }} as s
inner join expected as e
    on e.band = s.band
   and e.title_normalized = s.title_normalized
where s.release_year is distinct from e.earliest_year
