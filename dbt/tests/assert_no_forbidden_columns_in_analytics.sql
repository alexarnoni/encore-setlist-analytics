-- Nothing in `analytics` may carry per-show or per-setlist detail derived
-- from setlist.fm (docs/context/structure.md, spec-02a R7.2; list extended
-- for spec-03's show-grain intermediate concepts in item T9). This looks at
-- the columns the warehouse actually has, not at the model SQL, so a column
-- added by any future mart — or by a `select *` — is caught; it also covers
-- analytics.mart_song_survival/mart_survival_curves/mart_survival_summary
-- even though those are written directly by Python (D4), not built by dbt,
-- since it queries information_schema rather than a dbt ref. Returns the
-- offending columns; passes when it returns none.
select
    table_name,
    column_name
from information_schema.columns
where table_schema = 'analytics'
  and column_name in (
      'setlist_id', 'show_date', 'venue', 'song_name_raw',
      'show_key', 'show_id', 'show_index', 'setlist_url'
  )
