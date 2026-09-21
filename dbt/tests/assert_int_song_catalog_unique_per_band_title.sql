-- int_song_catalog must hold exactly one row per (band, title_normalized):
-- it is the join target for every performance, so a duplicate here would
-- silently double-count plays downstream (spec-02a item 12). Composite
-- key -> singular test. Passes when it returns no rows.
select
    band,
    title_normalized,
    count(*) as n
from {{ ref('int_song_catalog') }}
group by band, title_normalized
having count(*) > 1
