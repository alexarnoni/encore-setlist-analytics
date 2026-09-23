# Methodology notes

Definitions and known data limitations for Encore's numbers. The metric
rules themselves live in [`context/product.md`](context/product.md); this
file records what the data can and cannot support, so the public
methodology page (later spec) can be written from it.

## Rotation between shows

For each pair of consecutive shows by the same band and tour (ordered by
date, then by `setlist_id` on same-date shows — a deterministic but
arbitrary tie-break; shows without a date cannot be ordered and are left
out of both pairs and the show index), the setlist sets (every matched
song, including jams/solos/generic entries — see below) are compared with
the Jaccard index. **Rotation** for a tour is `1 - mean Jaccard` over its
pairs; a tour is only scored with **5 or more shows**. **Core songs** for a
tour are songs present in at least 90% of its shows. `mart_band_rotation_by_year`
assigns each pair to the year of its **second** show (a pair can straddle
New Year inside a tour) and excludes the same small tours as
`mart_tour_rotation`.

## Survival: duration, abandonment, censoring

Duration is measured **in band shows**, not calendar time, from a song's
live debut to its last appearance before it is dropped, **inclusive**:
`last_index - debut_index + 1`, so a song played in exactly one show has
duration 1. A song still in rotation at the end of the available history is
**censored** with the same rule applied up to the end: `total_shows -
debut_index + 1`.

**Abandonment** ("absent from the band's next N shows") is checked for
N = 25, 50 and 100. A **gap** is a run of N or more consecutive shows, fully
inside the history, without the song. A gap between two appearances is an
**intermediate gap** (the song came back); the run after the song's last
appearance is the **final gap**. The abandonment event is the **final gap
only**: the song is abandoned if its last appearance is at least N shows
before the end of the history (`total_shows - last_index >= N`), that is, it
left the setlist and did not return. Duration is then debut to that last
appearance. Every other song is **censored**: it is still being played, or it
left for a while and came back (matching the product rule, "censored if
fewer than N shows remain").

- A censored song that had at least one intermediate gap has duration debut
  to its last appearance.
- A censored song that never had a gap runs to the end of the history.
- `gaps_count` is the number of intermediate gaps at that N, and
  `returned_after_abandonment` is `gaps_count > 0`. Neither depends on the
  event: a song can return and later leave for good (an event with
  `returned_after_abandonment = true`).

**History of this rule.** The first version (spec-03 T6 to T14, 2026-09-21 to
2026-09-23) counted the **first** gap as the event. The first full run showed
what that does: a classic dropped for a tour and brought back was marked
abandoned at the first gap, so most debut-album songs still played today
(Kill 'Em All, Definitely Maybe, Hybrid Theory) appeared as events instead of
censored, with a duration cut at the first gap. On 2026-09-23 the rule was
changed to the final gap. Numbers from the earlier rule are not comparable.

**Eligibility** for survival analysis: a catalog song needs at least 3
**performances** (not distinct shows — a song played twice in one show
counts as 2 performances for eligibility, but durations are measured in
distinct shows) and must be matched either to a studio album
(`reference_album` not null) or to a recording with a known release year.
**Recording-only songs without a release year are not eligible** for
survival — there is no basis to place them on the catalog timeline.
Recording-only songs that do have a release year are eligible, under the
album label `non-album` (the same label used for era KPIs in
`product.md`). This is a for-now decision, to be revisited once real-run
numbers show how many songs it affects.

**Jams, solos and generic setlist entries** (e.g. `Helpless (jam)`,
matched as a recording-only catalog song) are **not filtered out** of
rotation or survival — the spec excludes them from catalog KPIs in
principle, but the data has no reliable jam/solo flag, so they are counted
as-is wherever they match the catalog. This can inflate set sizes, lower
Jaccard, and add spurious "songs" to survival tables. Recorded here as a
known limitation rather than patched with a filter.

## Known limitations

### Muse, 1994-1995: low catalog match (accepted)

In the first full run over all 7 bands, Muse's setlists for 1994 and 1995
matched the catalog poorly: 1994 has 9 performances with 0 matched, 1995 has
50 performances with 12 matched (24%). Together that is 59 of Muse's ~23,300
performances (0.25%), so the band's overall `match_rate_by_performance`
(0.9897) is barely affected. They are the only two band/year cells below
0.90 in the whole dataset (the next lowest is Linkin Park 2014 at 0.9065).

Likely cause: songs from the band's earliest demos and EPs that are not in
the MusicBrainz catalog the project keeps (studio albums, plus any recording
of the song). Not investigated song by song.

Decision (2026-09-21): **accepted as a known limitation.** Nothing is
patched or added to `seed_song_overrides.csv` for it. Those two years are
reported with their real, low match rate; any Muse KPI for 1994-1995 should
be read with that in mind and the methodology page should say so.

## Data handling of diagnostic output

The transform task logs, per band, the most frequent catalog songs without a
release year and the most frequent unmatched setlist titles, with counts (see
`dbt/README.md`). That is setlist.fm text, so it is handled like the raw data
it comes from, only more loosely:

- it is written to the Airflow task log only, never to a table, and never to
  the repository;
- task logs are kept for **7 days** and then deleted by the `log_cleanup` DAG,
  which is created active, not paused (retention was 14 days in spec-01 and
  was shortened on 2026-09-21);
- only aggregated results in `analytics` are persisted and published, as
  before. Setlist.fm titles never reach the marts. The one mart with a song
  column, `mart_song_survival`, carries the canonical MusicBrainz title of
  catalog songs (aggregation by song, allowed by `product.md`), never the raw
  setlist.fm text.
