-- Nothing in `analytics` may carry per-show or per-setlist detail derived
-- from setlist.fm (docs/context/structure.md, spec-02a R7.2). This looks at
-- the columns the warehouse actually has, not at the model SQL, so a column
-- added by any future mart — or by a `select *` — is caught. Returns the
-- offending columns; passes when it returns none.
select
    table_name,
    column_name
from information_schema.columns
where table_schema = 'analytics'
  and column_name in ('setlist_id', 'show_date', 'venue', 'song_name_raw')
