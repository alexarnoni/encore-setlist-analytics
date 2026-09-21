-- A song is in a show's set at most once: (show_key, song_key) is unique
-- (spec-03 T2). Passes when it returns no rows.
select
    show_key,
    song_key,
    count(*) as n
from {{ ref('int_show_song_sets') }}
group by show_key, song_key
having count(*) > 1
