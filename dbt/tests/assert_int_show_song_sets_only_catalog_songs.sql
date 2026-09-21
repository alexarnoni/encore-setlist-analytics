-- Every song in a setlist set is a catalog song of that band. Checked against
-- int_song_catalog directly (not through the is_matched flag the model uses),
-- so an unmatched title slipping into a set is caught. Passes when it returns
-- no rows.
select
    s.band,
    s.song_key
from {{ ref('int_show_song_sets') }} as s
left join {{ ref('int_song_catalog') }} as c
    on c.band = s.band
   and c.title_normalized = s.song_key
where c.band is null
