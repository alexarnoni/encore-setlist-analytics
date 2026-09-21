# Methodology notes

Definitions and known data limitations for Encore's numbers. The metric
rules themselves live in [`context/product.md`](context/product.md); this
file records what the data can and cannot support, so the public
methodology page (later spec) can be written from it.

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
