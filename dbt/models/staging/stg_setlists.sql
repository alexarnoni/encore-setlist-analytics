-- One row per show, from raw_setlistfm.setlists (spec-02a R2.1).
-- A view over ephemeral data: once the pipeline truncates the raw table
-- this returns zero rows rather than holding a stale copy.

with source as (

    select * from {{ source('raw_setlistfm', 'setlists') }}

),

renamed as (

    select
        setlist_id,
        band_name as band,
        {{ parse_setlistfm_date('event_date') }} as show_date,
        -- '' and NULL both mean "no tour"; the mart (not staging) decides
        -- to label those 'Unknown tour'.
        nullif(btrim(tour_name), '') as tour_name,
        venue_name as venue,
        city,
        country,
        setlistfm_url as setlist_url
    from source

)

select
    setlist_id,
    band,
    show_date,
    extract(year from show_date)::int as show_year,
    tour_name,
    venue,
    city,
    country,
    setlist_url
from renamed
