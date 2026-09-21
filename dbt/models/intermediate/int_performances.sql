-- One row per performed song (spec-02a R4.2), joined to int_song_catalog.
-- Tape entries and covers are excluded (R4.2); everything else is kept,
-- matched or not, so the unmatched share can be measured.
--
-- Matching key: normalize_title() of the raw setlist name — unless a
-- seed_song_overrides row maps that raw name to a canonical title, in
-- which case the CANONICAL title is the key (R4.3: overrides take
-- precedence over automatic matching). Both sides go through
-- normalize_title (R3.2).
--
-- A view over EPHEMERAL setlist.fm data: it carries setlist_id and song
-- names, which is fine in `intermediate` and never allowed in `analytics`.
--
-- `repertoire_age` is deliberately the plain SIGNED difference
-- (show_year - release_year). It is negative when a song was played
-- before its release year (an unreleased song at that show); how the
-- mart treats those is a separate decision, not made here.

with entries as (

    select *
    from {{ ref('stg_setlist_entries') }}
    where not is_tape
      and not is_cover

),

shows as (

    select setlist_id, show_date, show_year, tour_name
    from {{ ref('stg_setlists') }}

),

-- raw name -> canonical title, from the seed. One canonical per raw name
-- (assert_song_overrides_unique_raw_name fails otherwise; the row_number
-- only keeps the result deterministic if that test is ignored).
aliases as (

    select
        band,
        {{ normalize_title('raw_song_name') }} as raw_normalized,
        {{ normalize_title('canonical_song_title') }} as canonical_normalized,
        row_number() over (
            partition by band, {{ normalize_title('raw_song_name') }}
            order by canonical_song_title
        ) as rn
    from {{ ref('seed_song_overrides') }}
    where nullif(btrim(raw_song_name), '') is not null
      and nullif(btrim(canonical_song_title), '') is not null

),

keyed as (

    select
        e.setlist_id,
        e.band,
        s.show_date,
        s.show_year,
        s.tour_name,
        e.set_index,
        e.position,
        e.medley_part,
        e.is_encore,
        e.is_medley,
        e.song_name_raw,
        {{ normalize_title('e.song_name_raw') }} as raw_normalized
    from entries as e
    inner join shows as s on s.setlist_id = e.setlist_id

),

resolved as (

    select
        k.*,
        coalesce(a.canonical_normalized, k.raw_normalized) as title_normalized,
        a.canonical_normalized is not null as used_override_alias
    from keyed as k
    left join aliases as a
        on a.band = k.band
       and a.raw_normalized = k.raw_normalized
       and a.raw_normalized <> ''
       and a.rn = 1

)

select
    r.setlist_id,
    r.band,
    r.show_date,
    r.show_year,
    r.tour_name,
    r.set_index,
    r.position,
    r.medley_part,
    r.is_encore,
    r.is_medley,
    r.song_name_raw,
    r.title_normalized,
    c.song_title,
    c.reference_album,
    c.release_year,
    c.catalog_source,
    c.title_normalized is not null as is_matched,
    r.show_year - c.release_year as repertoire_age,
    r.used_override_alias
from resolved as r
left join {{ ref('int_song_catalog') }} as c
    on c.band = r.band
   and c.title_normalized = r.title_normalized
