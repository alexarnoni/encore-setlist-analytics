-- Production-sized synthetic setlists for PERFORMANCE checks only (about 7,000
-- setlists and 130,000 entries over the 7 bands, run_id = 'big'). Not used by the
-- correctness tests: it would mix with the scenario bands, so remove it with
--   delete from raw_setlistfm.setlist_entries where run_id = 'big';
--   delete from raw_setlistfm.setlists where run_id = 'big';
-- Needs the catalog built (intermediate.int_song_catalog). Isolated database only.
create temp table pool as
  select band, song_title, row_number() over (partition by band order by title_normalized) rn
  from intermediate.int_song_catalog where song_title ~ '^[A-Za-z0-9][A-Za-z0-9 ,.!?''&-]{2,60}$';
insert into raw_setlistfm.setlists (setlist_id, artist_mbid, band_name, event_date, tour_name, venue_name, city, country, setlistfm_url, run_id)
select 'big-'||g, 'x',
       (array['Metallica','Muse','Oasis','Linkin Park','Arctic Monkeys','Avenged Sevenfold','Twenty One Pilots'])[1+g%7],
       to_char(date '2001-01-01' + (g*2), 'DD-MM-YYYY'), 'Tour '||(g/60), 'v','c','XX','http://x/'||g,'big'
from generate_series(1,6500) g;
insert into raw_setlistfm.setlist_entries (setlist_id,set_idx,position,song_name,is_encore,is_cover,cover_artist,is_tape,run_id)
select 'big-'||g, 0, p,
       case when p % 10 = 0 then 'Zzz Unmatched '||(g % 50) else pool.song_title end,
       false,false,null,false,'big'
from generate_series(1,6500) g cross join generate_series(1,20) p
left join pool on pool.band = (array['Metallica','Muse','Oasis','Linkin Park','Arctic Monkeys','Avenged Sevenfold','Twenty One Pilots'])[1+g%7]
              and pool.rn = 1 + ((g*31 + p*17) % 150)
where p % 10 = 0 or pool.song_title is not null;
analyze raw_setlistfm.setlists; analyze raw_setlistfm.setlist_entries;
