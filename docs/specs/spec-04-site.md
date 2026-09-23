# Spec 04: Public static site

Read the context files in `docs/context/`, `docs/methodology.md` and `docs/specs/spec-03-rotation-survival.md` before starting. This spec turns the existing marts into a public, bilingual static site published on Cloudflare Pages.

## Goal

A static site generated from the `analytics` marts, in Brazilian Portuguese and English, published at `encore.alexarnoni.com`. No API, no backend, no database access at runtime.

## Working rules

- Branch `spec-04`, same worktree approach as spec 03.
- The generator reads only the `analytics` schema. It must never touch raw schemas.
- Build output goes to `site/` and is gitignored. Deploy is a separate, explicit step.
- No setlist.fm request is made at any point.

## Requirements

### R1. Generator
1. `src/encore/site/build.py`, runnable as `python -m encore.site.build`, reading the marts and writing `site/`.
2. Jinja2 templates in `src/encore/site/templates/`, static assets in `src/encore/site/assets/`.
3. Charts rendered as **inline SVG** with matplotlib, the same styling used in the notebooks. No JavaScript chart library and no runtime data fetching.
4. Every generated page includes the build date and the pipeline run date the data came from.

### R2. Localisation
1. Two locales: `pt-BR` (default) and `en`. Output at `site/pt/...` and `site/en/...`, with `site/index.html` redirecting to `/pt/`.
2. All user-facing strings live in `src/encore/site/locales/pt-BR.yml` and `en.yml`. No hardcoded text in templates.
3. Band names, album names and tour names are never translated.
4. A language switcher on every page, preserving the current page.
5. `<html lang>` set per locale, and `hreflang` links between the two versions.

### R3. Pages
1. **Home**: what the project is, the three headline findings with one chart each, and links to the band pages.
2. **Band page** (one per band, 7 total): repertoire age by year, rotation by year, Kaplan-Meier curves by album, the album table (songs, abandoned, censored, median), and two or three sentences of findings specific to that band.
3. **Comparison page**: all bands together for repertoire age and rotation, plus the median survival table.
4. **Methodology**: KPI definitions, the abandonment rule and the N sensitivity table, data policy (why raw data is not stored), known limitations, and match quality by band.
5. **About**: what the project is for, the stack, and a link to the GitHub repository.

### R4. Findings text
Findings are written by hand in the locale files, not generated. Numbers inside them are placeholders filled from the marts at build time (for example `{{ metallica_median }}`), so the text never goes stale silently. If a placeholder has no value, the build fails.

### R5. Attribution and policy
1. Every page that uses setlist.fm derived data shows attribution with a followable link to setlist.fm, in the HTML, without `nofollow`.
2. MusicBrainz credited as CC0.
3. No page shows individual setlists, show dates, venues or setlist.fm identifiers. Song titles are canonical MusicBrainz titles, as already allowed.
4. A build-time check fails if any generated page contains a forbidden field name or a date more precise than a year.

### R6. Design and accessibility
1. Responsive, readable on mobile, no horizontal scrolling.
2. Light and dark mode through `prefers-color-scheme`, with the same band colour per band in both.
3. Each chart has a text alternative (a short summary or a data table) so the page works without images.
4. Keep the total page weight small. No web fonts unless self-hosted.

### R7. Deploy
1. `make site` builds into `site/`.
2. `make site-serve` serves it locally for review.
3. Deploy to Cloudflare Pages as an explicit manual step, documented in the README (Wrangler direct upload or the Pages dashboard).
4. Custom domain `encore.alexarnoni.com`, with the DNS step documented.
5. The site is not rebuilt automatically by the pipeline in this spec. After a pipeline run, `make site` is run by hand.

### R8. Tests
1. Unit tests for the generator with a fake marts fixture: every page is produced, both locales exist, no missing translation key, no unfilled placeholder.
2. A test that fails if a forbidden column name or a full date appears in the output.
3. A link check over the generated site (no broken internal links).

## Acceptance criteria

- `make site` produces both locales with all pages from real marts.
- Every page passes the forbidden content check.
- The site renders correctly on a phone-sized viewport and in dark mode.
- The published site is reachable at encore.alexarnoni.com.
- Tests pass.

## Out of scope

- Interactive charts, search and filtering
- API and dynamic backend
- Automatic rebuild and deploy from the pipeline
- The deferred KPIs (set position, geography, era weights)
