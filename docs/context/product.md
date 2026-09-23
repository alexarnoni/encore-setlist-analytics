# Product: Encore

Encore is a non-commercial data portfolio project that measures how bands use their own catalog in live shows over their careers.

## Questions the product answers

1. Does the band live off its past or bet on new material?
2. Do shows change from night to night or stay the same?
3. How long does a song survive in the live repertoire after release?
4. How is a show structured (opener, main set closer, encore) and does that change over time?
5. Does the repertoire change by country or venue type?

## Bands (fixed scope for v1)

Arctic Monkeys, Oasis, Linkin Park, Twenty One Pilots, Muse, Metallica, Avenged Sevenfold.

## Data sources

- setlist.fm API: show history and setlists. Non-commercial use only. Raw data is ephemeral (see Data policy).
- MusicBrainz API: discography (albums, tracks, recordings, release dates). CC0, can be stored.

## Data policy (non-negotiable)

- Raw setlist.fm data exists only during a pipeline run and is deleted at the end of the run.
- Only aggregated results (by band, tour, album, song) are persisted and published. A song-level mart may carry the canonical MusicBrainz title of a catalog song (CC0 data, for example `mart_song_survival.song_title`); it never carries setlist.fm text, dates, show ids or setlist URLs.
- No per-show setlist pages. When a show is referenced, link to its setlist.fm page.
- Every page that uses setlist.fm data shows attribution with a setlist.fm link (no nofollow, present in the HTML).
- The repository never contains setlist.fm data, including notebook outputs.
- The API key is never committed or shared.

## Key metric rules

- Covers, tape entries, intros, jams and solos are excluded from catalog KPIs.
- Medleys (names joined by " / ") are split into separate entries flagged is_medley.
- Song abandonment: the song leaves the band's setlist and does not return, i.e. its last appearance is at least 50 shows (N = 50) before the end of the history. Songs still played, and songs that were absent for 50 or more shows but came back, are censored. Intermediate gaps are counted (`gaps_count`), not treated as abandonment.
- Survival analysis uses catalog songs only (matched to studio album, single, EP or B-side).
- Reference album of a song: earliest studio album containing it.
- Main data quality metric: % of performances (weighted by plays) matched to the catalog (`match_rate_by_performance`). `match_rate_by_album` (share of performances matched to a studio album) is a secondary, informational column and never replaces the main metric.
- Era KPIs: songs matched to the catalog but not to a studio album (singles, B-sides, other recordings) form their own category, "non-album", instead of being dropped.
- Song release year: repertoire age uses the song's first official release year, the earliest between the reference album's year and the recording's first release date. The reference album remains the basis for era KPIs.
- Suspicious release dates: a warn-level check lists songs whose recording date is more than 2 years earlier than the album year, so the MusicBrainz dates can be reviewed and fixed through the override seed.
- Known data limitations (for example Muse 1994-1995 matching poorly) are recorded in `docs/methodology.md`.

## Audience

Recruiters and hiring managers for data engineering and analytics engineering roles in Europe. Clarity of method matters as much as the charts.
