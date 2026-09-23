# Spec 04 — Progress and implementation plan

Tracks `docs/specs/spec-04-site.md` (public bilingual static site). Same
discipline as specs 01 to 03: small tasks, one commit each, results recorded
here.

> **STATUS: plan approved 2026-09-23 (see section 3, answers). T0 done, T1 in progress. T12 stops for review of the findings text.**
> Work happens only on branch `spec-04`, in the worktree
> `D:\projetos\encore-spec04` (main directory stays on `master`).

## 1. Guardrails

- The generator reads only `analytics.*`, through a read-only session and a
  table allowlist (the pattern notebook 02 already uses). It never imports the
  ingestion clients, so no setlist.fm request is possible.
- `site/` is gitignored. Deploy to Cloudflare Pages is a manual step the user
  runs; this plan never deploys.
- Unlike spec 03, nothing here writes to the database, so no disposable
  database is needed: real-data builds read the real `analytics` marts
  (127.0.0.1:5435). Unit tests use a fake-marts fixture and need no database.
- The main stack (containers, image, DAG) is not touched. No `docker compose`
  from the branch.

## 2. Facts checked while planning (2026-09-23)

- Worktree: spec 03's `D:\projetos\encore-spec03` no longer exists, so a fresh
  one was created: `git worktree add -b spec-04 ../encore-spec04 master`, with
  `.env` copied in (gitignored). `spec-04-site.md` was untracked on `master`;
  it was copied into the worktree and is still untracked in both places (it
  gets committed with this plan once approved).
- Marts available in `analytics`: `mart_repertoire_age`
  (band/tour/year), `mart_band_rotation_by_year`, `mart_tour_rotation`,
  `mart_match_quality` (band/year), `mart_song_survival`,
  `mart_survival_curves` and `mart_survival_summary` (band × album × N in
  25/50/100; album `all` is the band total, `non-album` its own category).
- `requirements.txt` has matplotlib, PyYAML, psycopg2 but **not Jinja2**; it is
  added. Chart styling (band colours, palette, ink/surface/neutral) currently
  lives inside notebook 02; it is extracted into `src/encore/site/theme.py`.
- `Makefile` only wraps docker compose today; `site` and `site-serve` are new
  targets. `make` on Windows runs in WSL (README).
- Repo remote: `github.com/alexarnoni/encore-setlist-analytics` (for the About
  page link).

## 3. Open points (need an answer or confirmation before the tasks that depend on them)

| # | Point | Proposed resolution |
|---|---|---|
| Q1 | **R1.4 vs R5.4.** Every page must show a build date and a pipeline run date, but the content check must fail on "a date more precise than a year". | The two stamps are the only permitted full dates. They are rendered inside one marked element (`<footer data-build-stamp>`) and the check strips that element before scanning; everywhere else a full date still fails. Affects T11. |
| Q2 | **"Pipeline run date the data came from"** lives in `ops.pipeline_runs`, but R1 says the generator reads only `analytics`. | Use `max(computed_at)` over the marts (already in `analytics`, same run). `ops` is not read. |
| Q3 | **The three headline findings** for the home page are not named in the spec. | Proposal, matching product questions 1, 2 and 3: (a) repertoire age (past vs new), (b) rotation (night to night), (c) median song survival by band. Decided after the real numbers are seen (T12); the text is yours to approve. |
| Q4 | **Findings text** is "written by hand". | I draft pt-BR and en from the real marts in T12 and you review before it is committed; nothing is auto-generated. |
| Q5 | **Repertoire age by year per band** must be aggregated from a tour × year mart. | Performance-weighted mean of `avg_repertoire_age` using `aged_performances` (exact). The median is not aggregatable from the mart, so the site shows the mean only and says so. |

**Approved answers (2026-09-23).** Q1 and Q2 as proposed. Q5 extended: besides
the weighted mean per year, the band page also shows the **median where it
genuinely exists, per tour**, in a bar chart (`mart_repertoire_age` carries
`median_repertoire_age` per band/tour/year; a tour spanning several years uses
its per-year cells, no fake aggregation), rather than only disclaiming it.
Q3 headlines, fixed: (1) a new album makes a band younger on stage, but only
for a while (Metallica: Death Magnetic, Hardwired, 72 Seasons; also Avenged
Sevenfold and Linkin Park); (2) bands settle into a fixed show as they grow,
Metallica the exception (rotation about 0.10 in the eighties to 0.86 on M72);
(3) about a third of a catalog becomes permanent and the rest passes through
(Oasis near 36%, Morning Glory 89%, 2000s albums below 30%). Numbers in these
claims are checked against the real marts in T12 before the text is final.
Q4: drafted in T12, then review. Jinja2 approved for requirements.

## 4. Design decisions

**D1 — Package layout** (`src/encore/site/`): `build.py` (entry point),
`marts.py` (read-only loader, allowlist), `shape.py` (aggregations, pure
functions on DataFrames), `charts.py` + `theme.py` (matplotlib to SVG),
`i18n.py` (locale loading, strict placeholders), `policy.py` (content check),
`templates/`, `assets/` (one CSS file, inlined or linked, no web fonts),
`locales/pt-BR.yml`, `locales/en.yml`.

**D2 — Themes and inline SVG (revised 2026-09-23, R6.2 changed).** Light by
default with a header toggle; the choice lives in `localStorage` (reads and
writes in try/catch, page works without it). Initial value: stored choice, else
`prefers-color-scheme`, else light. A few lines of inline script in `<head>`
set `data-theme` on `<html>` before first paint (no flash); the toggle button
flips it and stores it. Without JS, CSS falls back to
`prefers-color-scheme` through `:root:not([data-theme])`. Colours are tokens on
`:root` and `:root[data-theme="dark"]`. matplotlib writes fixed colours, so
charts are drawn with sentinel colours and post-processed into CSS custom
properties (`var(--band-muse)`, `var(--ink)`, ...) that follow the active
theme, so a toggle recolours charts with no re-render. The same band keeps the
same hue in both themes, chosen so it holds contrast against both surfaces
(checked in T5). `svg.fonttype: none` keeps text as text. This is the only
JavaScript on the site (no chart library, no data fetching, R1.3).

**D3 — Accessibility.** Each chart is a `<figure>` with `role="img"`,
`<title>`/`<desc>` and a `<details>` data table (years/values, or median
table) so the page works without images.

**D4 — Strict localisation.** Jinja `StrictUndefined`; the build fails on a
missing key in either locale, a key present in one locale only, or an unfilled
`{{ placeholder }}` in findings (R4). Band, album and tour names are read from
the marts and never pass through the locale files.

**D5 — Output.** `site/index.html` (redirect to `/pt/`), `site/{pt,en}/index.html`,
`bands/<slug>/`, `comparison/`, `methodology/`, `about/`. Directory-style URLs
so Cloudflare Pages serves them without rewrites.

## 5. Tasks

Each task is one commit, run `pytest` before declaring it done.

| Task | What | Files | Verification |
|---|---|---|---|
| **T0** | Workspace: worktree, `.env`, spec copied. **Done** in this planning step. | — | `git worktree list` shows `encore-spec04` on `spec-04`; main directory still on `master`. |
| **T1** | Skeleton: package, Jinja2 in requirements, `site/` in `.gitignore`, empty `python -m encore.site.build` that logs and exits. | `requirements.txt`, `.gitignore`, `src/encore/site/{__init__,__main__,build}.py` | `python -m encore.site.build` runs; `git status` shows `site/` ignored. |
| **T2** | Read-only marts loader with table allowlist; fake-marts fixture (all 7 bands, a few years, all three N) shaped like the real marts. | `src/encore/site/marts.py`, `tests/site/fixtures.py`, `tests/site/test_marts.py` | Test: non-allowlisted table refused, session is read-only, fixture columns equal the dbt/io column lists. Real read of the 7 marts smoke-checked. |
| **T3** | Locale layer: load both YAMLs, key-parity check, strict placeholder fill (Q4/R4), locale-aware number formatting. | `src/encore/site/i18n.py`, `locales/*.yml` (skeleton), `tests/site/test_i18n.py` | Tests: missing key, extra key, unfilled placeholder each fail the build. |
| **T4** | Data shaping: repertoire age by year (Q5), rotation by year, KM curves, album table, median table, N sensitivity table, match quality by band, headline numbers as placeholder values. | `src/encore/site/shape.py`, `tests/site/test_shape.py` | Tests against the fixture with hand-computed expected values (weighted mean, medians `not reached`, `all`/`non-album` handling). |
| **T5** | Chart theme + SVG renderer: theme extracted from notebook 02, sentinel-colour post-processing (D2), text alternative per chart (D3), band colours checked for contrast on both surfaces. | `theme.py`, `charts.py`, `tests/site/test_charts.py` | Tests: output is inline `<svg>`, contains no hex colours outside the CSS variables, has `<title>`/`<desc>`, and is deterministic. Contrast check of each band colour against both surfaces. Visual check of one chart of each type in the browser pane in both themes, toggled live. |
| **T6** | Base template + CSS: layout, language switcher preserving the page, `<html lang>`, hreflang, footer with build/run stamps (Q1/Q2), setlist.fm and MusicBrainz (CC0) attribution, `site/index.html` redirect, mobile styles, theme toggle in the header with pre-paint init script and localStorage persistence (D2). | `templates/base.html`, `assets/site.css`, `build.py` | Tests: both locales get the same page set, every page has `lang`, hreflang pair, a followable setlist.fm link without `nofollow`, a toggle button in the header, and a head script that sets `data-theme` from localStorage, else `prefers-color-scheme`, else light. |
| **T7** | Methodology and About pages (content from `docs/methodology.md`, sensitivity table, match quality by band, data policy, known limitations incl. Muse 1994-1995 and shows-vs-time, stack, GitHub link). | templates, locale files | Tests: pages exist in both locales; sensitivity table numbers equal the fixture; a real build shows the same numbers as `docs/methodology.md`. |
| **T8** | Comparison page: repertoire age and rotation for all bands, median survival table. | template, `charts.py` use | Page in fixture build; no-JS text alternative present. |
| **T9** | Band pages (7): age by year, rotation by year, KM by album, album table, findings placeholder slot. | template, `build.py` | One page per band and locale; album table equals `mart_survival_summary`; min-songs/min-pairs handling matches the notebook (hollow points, albums under 5 songs not drawn). |
| **T10** | Home page: project intro, three headline findings with a chart each, links to band pages. | template | Links resolve (T13). |
| **T11** | Content policy check at build time (R5.4): forbidden field names (setlist_id, show_id, venue, url, etc., from the dbt forbidden-columns test) and full dates outside the stamp element. Wired into `build.py` so the build fails. | `src/encore/site/policy.py`, `tests/site/test_policy.py` | Tests inject a forbidden name and an ISO date into an otherwise valid page and the check fails; the stamp alone passes. |
| **T12** | Findings text: draft pt-BR and en for each band and the three headlines using placeholders (R4), from the real marts. **Stops for your review of the text.** | `locales/*.yml` | Build fails if a placeholder has no value (test); real build fills them; you approve wording. |
| **T13** | Link check over the generated site (internal links, anchors, hreflang targets, switcher targets). | `tests/site/test_links.py` | Passes on fixture build; a deliberately broken link fails it. |
| **T14** | `make site` and `make site-serve` (127.0.0.1 only, never 0.0.0.0), README section: build, review, Wrangler direct-upload or dashboard deploy, DNS for `encore.alexarnoni.com`, "rebuild by hand after a pipeline run". | `Makefile`, `README.md` | `make site` and `make site-serve` work (via WSL or the venv); README steps read cleanly. |
| **T15** | Real-data build and review: all pages, both locales, forbidden check passes on real output, page weight measured, phone-sized viewport (375px) and both themes checked in the browser pane, toggle and persistence exercised, no horizontal scroll. | — (fixes as needed) | Recorded here: page count, total KB per page, screenshots reviewed, `pytest` green. |
| **T16** | Acceptance and handoff: acceptance list checked, merge to `master`. The **deploy and DNS are yours**; I stop after documenting them. | this file | Checklist below. |

## 6. Acceptance checklist (from the spec)

- [ ] `make site` produces both locales with all pages from real marts
- [ ] Every page passes the forbidden content check
- [ ] Phone-sized viewport and both themes render correctly; toggle works and persists across reloads
- [ ] Tests pass
- [ ] Published at encore.alexarnoni.com (manual step, user)

## 7. Task log

_T0 done._



**R6.2 changed (2026-09-23).** Light default plus a header toggle with localStorage persistence replaces pure `prefers-color-scheme`. Spec and D2 updated; affects T5, T6 and T15.
