# Spec 02a — Implementation progress

> **STATUS: CLOSED — spec 02a accepted on 2026-09-21.** All 22 items are
> done and the acceptance run passed (Oasis `match_rate_by_performance`
> 0.9999, idempotent marts, `raw_setlistfm` empty, all dbt tests green).
> This file is no longer edited. The two questions that were still open at
> acceptance were decided afterwards (see the last two entries of the
> decisions log) and the resulting follow-up work is tracked in
> `docs/specs/spec-02a-followup-progress.md`.

Tracks the approved plan for `docs/specs/spec-02a-first-kpi.md`. Updated
and committed at the end of every task, marking items done and recording
decisions made along the way (versions pinned, schema choices,
deviations from the spec text) — same discipline as
`docs/specs/spec-01-progress.md`.

## Adjustments approved before implementation started

1. Item 1: the dev load must record its load timestamp in `ops` (or a
   simple table) and the README must state this data is temporary and
   must not be left in the database between work sessions. Item 22 must
   still end with `raw_setlistfm` empty.
2. Item 2: `dbt/profiles.yml` must contain only `env_var()` references,
   never literal credentials — verified no secret ends up in the repo.
3. Item 3: create the `unaccent` extension in `infra/postgres/init/`
   instead of a dbt `on-run-start` hook (`CREATE EXTENSION` needs
   superuser, which the app's runtime role won't have). The dbt hook
   may only check the extension exists and fail with a clear message if
   it doesn't.
4. Item 6: dbt unit tests apply to models, not macros directly. Cover
   `normalize_title` with a small test model applying the macro to
   fixed input values, plus a singular test comparing expected outputs.
5. Item 22: if `match_rate_by_performance` for Oasis is below 0.90,
   list the unmatched titles ordered by performance count and **stop
   for review** — do not fill `seed_song_overrides.csv` unilaterally.

## Open questions raised before implementation started

Flagged when the plan was proposed; resolved one way or another before
or during the corresponding task, with the actual resolution recorded
in the decisions log below.

1. **Medley split positions** (R2.2): the spec doesn't say how multiple
   rows born from splitting one `" / "`-joined entry share/subdivide
   `position`. Proposed default: each part keeps the original
   `position` and gets a new `medley_part` (1, 2, 3...) to disambiguate
   within the group.
2. **`dbt seed` "only when changed or on first run"** (R8.1): real
   change detection (hashing the seed CSVs) is more machinery than two
   small seed files justify. Proposed default: run `dbt seed` on every
   `transform` task — idempotent, negligible cost.
3. **Seed schema**: the spec doesn't say which schema seeds load into.
   Proposed default: `staging`, alongside the models that consume them.
4. **Local dbt development against ephemeral raw data**: `raw_setlistfm`
   is truncated at the end of every pipeline run, so staging models
   can't be iterated against real data without either running the full
   DAG repeatedly (spending real API quota each time) or loading data
   once and leaving it in place. Resolved by task 1 below: a one-off
   direct load (bypassing the DAG's cleanup) used for all subsequent
   local dbt work.

## Checklist

- [x] **1. Dev fixture: load real Oasis raw data without truncating** —
      `scripts/load_dev_fixture.py` calls
      `encore.ingestion.setlistfm.extract_band` +
      `encore.ingestion.musicbrainz.extract_band` directly against
      local Postgres, bypassing the DAG (and its cleanup). MusicBrainz
      extraction uses the default 30-day freshness check (not forced),
      so it naturally skips re-fetching Oasis's discography — already
      loaded by spec-01 item 25 — instead of spending quota again for
      data already in place. Load timestamp recorded via
      `ops.log_run(..., status="dev-fixture")` (adjustment 1) rather
      than a new table: reuses `ops.pipeline_runs` with a status value
      distinct from `"success"`/`"failed"`, so
      `estimate_next_run_setlistfm_cost()`'s `status='success'` filter
      ignores it (doesn't skew the real budget estimate) while
      `sum_setlistfm_requests_today()` still counts it (the requests
      were real). `dbt/README.md` (new, minimal — expands in item 5)
      states the data is temporary and gives the exact truncate command.
      **Verified for real**: ran the script against local Postgres —
      loaded 958 setlists/13,170 entries (matches spec-01 item 25's
      numbers exactly), MusicBrainz step correctly skipped (0
      requests), `ops.pipeline_runs` shows the `dev-fixture` row with
      timestamp, request counts and `setlists_per_band`.
- [x] **2. dbt project scaffold** — `dbt/dbt_project.yml`,
      `dbt/profiles.yml`. `profiles.yml` has zero literal credentials —
      every connection value is `env_var(...)` except `dbname: encore`
      (a fixed application constant, not a secret, matching
      `encore.db.DATABASE_NAME`) and `schema: staging` (the harmless
      default; every model's real schema is set per-layer in
      `dbt_project.yml`, see below). Verified nothing secret is in the
      repo by reading the committed file back — plain `env_var()` calls
      only (adjustment 2).
      `dbt/macros/generate_schema_name.sql` overrides dbt's default
      schema-naming (which would otherwise concatenate the profile's
      target schema with each custom schema, e.g. `staging_analytics`
      instead of `analytics`) — needed for `dbt_project.yml`'s
      per-layer `+schema:` config (staging/intermediate = view,
      analytics = table) to produce the exact schema names in
      `structure.md`. `models/`, `seeds/`, `tests/` directories are not
      pre-created empty (git doesn't track empty dirs; dbt doesn't
      require them to pre-exist) — they'll appear with their first real
      file in items 4/6/7.
      **Verified for real**: `dbt debug` (via the Docker image's
      `/opt/dbt-venv/bin/dbt`, `dbt/` mounted since it isn't copied into
      the image until item 19) connects successfully to the real
      `encore` database.
- [x] **3. Enable the `unaccent` Postgres extension** —
      `infra/postgres/init/03_create_unaccent_extension.sh` (adjustment
      3: `CREATE EXTENSION` needs superuser; only runs on an empty
      volume, same limitation as items 2/6 in spec-01). The dbt
      `on-run-start` hook (`dbt/macros/assert_unaccent_extension_exists.sql`,
      wired in `dbt_project.yml`) only checks the extension exists and
      raises a clear compiler error if it doesn't — it never tries to
      create it.
      **Verified both states for real** against the dev Postgres (which
      predates this script, so the init-on-empty-volume path couldn't
      be exercised directly): ran the macro via `dbt run-operation
      assert_unaccent_extension_exists` *before* the extension existed
      → failed with the exact intended message; created the extension
      manually (`CREATE EXTENSION IF NOT EXISTS unaccent`); re-ran the
      same command → passed silently. Note: `dbt run`/`build` currently
      report "Nothing to do" and skip `on-run-start` hooks entirely
      since there are still zero models/seeds — the hook only actually
      fires once item 4+ gives dbt something to run.
- [x] **4. Seeds** — `dbt/seeds/seed_album_exclusions.csv` (5 rows) and
      `dbt/seeds/seed_song_overrides.csv` (header only). The exclusion
      titles are the exact strings from the Phase 0 notebook's
      `ALBUNS_EXCLUIR` dict (not retyped from the spec's prose
      descriptions, which are paraphrases — e.g. the spec says "Oasis
      Manchester 1994" but the real MusicBrainz title is
      `Definitely Maybe Tour - 1994-12-18 - Manchester Academy -
      Homedown Showdown`); the Avenged Sevenfold one contains commas so
      it's quoted in the CSV. `dbt_project.yml` now pins every seed
      column to `text` explicitly: dbt infers seed types from the data,
      so a title like "1984" would silently become an integer, and the
      overrides seed is empty (header only) so inference has nothing to
      work from.
      **Verified for real**: `dbt seed` → `INSERT 5` and `INSERT 0`;
      `information_schema` confirms every column is `text`; a join of
      the exclusions against `raw_musicbrainz.albums` shows both Oasis
      titles match exactly 1 real album each (the Muse/A7X/Metallica
      ones show 0 only because those bands aren't loaded yet).
      **Also resolved the item-3 pending note**: this `dbt seed` run is
      the first one with something to run, and the `on-run-start` hook
      fired for real (`1 of 1 OK hook: encore.on-run-start.0`).
- [x] **5. `dbt/README.md`** — layout/schema table, prerequisites
      (including the `unaccent` caveat for databases that predate the
      init script), how to run dbt locally via the Airflow image's
      `/opt/dbt-venv` (dbt isn't in the project venv), and the
      dev-fixture section from item 1. The "inside Airflow" section
      says explicitly that it is **not wired up yet** (items 19-20)
      rather than describing behaviour that doesn't exist; revisit in
      item 20.
      **Verified by executing the README, not just writing it** — and
      that caught two bugs in my first draft: (1) `dbt debug` exited 2
      because it doesn't accept `--target-path` (only some subcommands
      do), so artifact redirection moved to the `DBT_TARGET_PATH` /
      `DBT_LOG_PATH` env vars, which work for every subcommand; (2)
      dbt kept dropping a `.user.yml` (anonymous-user id) into `dbt/`
      next to `profiles.yml`, fixed with
      `DBT_SEND_ANONYMOUS_USAGE_STATS=false`. Final check extracted the
      `dbt()` function verbatim from the committed README with `awk`
      and ran `debug`/`seed`/`run`/`test` through it: all exit 0, and
      `dbt/` contains only tracked files afterwards. (`run` and `test`
      exit 0 with "Nothing to do" until models exist in item 7.)
- [x] **6. `normalize_title(column)` macro** —
      `dbt/macros/normalize_title.sql`. Per adjustment 4 there is no
      `unit_tests:` block (those apply to models): the macro is exercised
      by `dbt/models/staging/test_fixtures/test_normalize_title_cases.sql`
      (25 literal inputs with hand-written expected outputs, plus the
      macro's `actual_title`) and the singular test
      `dbt/tests/assert_normalize_title_expected_outputs.sql`, which
      returns any row where `actual_title is distinct from
      expected_title` (`is distinct from` so NULL -> NULL compares
      equal). The macro builds its expression one rule per Jinja
      variable, in this order: lowercase+unaccent, apostrophes removed
      without a space, `&` -> `and`, edition segments dropped, trailing
      `feat.` clause dropped, remaining punctuation -> space,
      whitespace collapsed. (My first version was one deeply nested
      call and I miscounted the parentheses by hand — rewritten as
      stepwise variables before it ever ran.)
      **Verified for real, and the test itself verified**: `dbt run` +
      `dbt test` passed; read back all 25 actual outputs from the view
      (not just the pass/fail); then injected a regression (apostrophes
      -> space instead of nothing) and confirmed the test FAILS with 5
      rows, then restored the macro (`diff` against the backup empty)
      and confirmed it passes again. Caveat found doing that: the two
      `Rock 'n' Roll Star` cases still pass under the regression (the
      extra space collapses to the same string), so they don't actually
      discriminate the "no space" rule — the five other apostrophe
      cases (`Don't` x2, `Editor's`, `What's`, `Ain't`) do.
- [x] **7. `stg_setlists`** — `dbt/models/staging/stg_setlists.sql`
      plus `_sources.yml` declaring `raw_setlistfm.setlists` as a dbt
      source (the other raw tables get declared as items 8-10 need
      them). Columns exactly as R2.1: `setlist_id, band, show_date,
      show_year, tour_name, venue, city, country, setlist_url`.
      `tour_name` is `nullif(btrim(...), '')` so an empty string and NULL
      both mean "no tour"; labelling those `Unknown tour` is the mart's
      job (R5), not staging's.
      **Scope addition, flagged**: profiled the raw data first (all 958
      Oasis dates are valid `DD-MM-YYYY`), but Postgres `to_date()` /
      `make_date()` RAISE on an impossible date (`31-02-2001`) rather
      than returning NULL, and these are views — one bad date in any of
      the six not-yet-loaded bands would only blow up when a downstream
      mart is built, failing the whole pipeline run. Phase 0 treated an
      invalid date as NaT. So added `dbt/macros/parse_setlistfm_date.sql`
      (nested `CASE`s, because Postgres doesn't guarantee `AND`
      short-circuiting but does evaluate a `THEN` only when its `WHEN`
      matched) with the same fixture-model + singular-test pattern as
      item 6: `test_parse_setlistfm_date_cases` (17 cases: valid, leap
      day, non-leap Feb 29, April 31, day/month/year 0, month 13,
      wrong shapes, empty, NULL) and
      `assert_parse_setlistfm_date_expected_outputs`.
      **Verified for real**: `dbt run` + `dbt test` green; read back all
      17 actual date outputs; reconciled `stg_setlists` against
      `raw_setlistfm.setlists` — 958 rows / 958 distinct ids (same as
      raw), zero null `show_date`/`show_year`, min/max
      1991-08-14/2025-11-23 (matches the raw profile), 169 null
      `tour_name` (matches), and 0 rows where any mapped column differs
      from the raw value. Test verified too: removed the day-of-month
      guard from the macro and the test went red with `ERROR: date field
      value out of range: 2023-02-29` (the exact failure the macro
      exists to prevent), then restored it (`diff` identical) and
      confirmed green again.
- [x] **8. `stg_setlist_entries`** — `dbt/models/staging/stg_setlist_entries.sql`;
      the split lives in `dbt/macros/split_medley.sql` (a lateral
      subquery over `string_to_array(..., ' / ')` +
      `unnest ... WITH ORDINALITY`) so it can be tested in isolation.
      Columns: R2.2's nine plus `medley_part`. Resolves open question 1
      as proposed: every part of a medley keeps the original `position`
      and `set_index`, and `medley_part` (1, 2, ...) tells siblings
      apart — `(setlist_id, set_index, position, medley_part)` is a
      unique key. Flags (`is_tape`/`is_cover`/`is_encore`) are
      inherited by every part. `is_medley = part_count > 1`, with empty
      pieces dropped *before* numbering, so `A /  / B` is a 2-part
      medley numbered 1, 2 (no gap) and a trailing `Song / ` is a
      1-part non-medley.
      **Real data caveat, stated plainly: the Oasis data contains zero
      medleys** (0 of 13,170 entries contain `" / "`), so the split
      logic cannot be exercised on real rows. It is covered only by
      the synthetic fixture `test_split_medley_cases` (11 inputs: plain,
      2- and 3-part, whitespace, bare-slash `AC/DC`, empty piece,
      trailing separator, keyword-looking title, `''`, blank, NULL) and
      `assert_split_medley_expected_outputs`, which diffs actual against
      hand-written expected rows in both directions. Also unverified:
      that setlist.fm really uses `" / "` for medleys — that convention
      comes from `product.md`, and no medley appears in this data to
      confirm it. Worth checking when another band is loaded.
      **Decision, flagged**: entries with an empty/blank name produce no
      rows (they aren't identifiable songs). 3 of Oasis's 13,170 raw
      entries; 2 of those 3 were `is_tape` and would have been excluded
      from the KPIs anyway.
      **Verified for real**: `dbt run` + `dbt test` green; read back all
      13 fixture rows; reconciled against raw — 13,170 raw − 3 blank =
      13,167 staging rows; tape 531 → 529 (exactly the 2 dropped tape
      entries), cover 729 and encore 1,593 unchanged; 0 unique-key
      violations; 0 rows whose name differs from the raw trimmed name.
      Test verified: removed the empty-piece filter from the macro and
      the test failed with 9 rows, restored (`diff` identical), green.
- [x] **9. `stg_albums` + `stg_album_tracks`** —
      `dbt/models/staging/stg_albums.sql` (`release_group_mbid,
      band_mbid, band, album_title, first_release_date, release_year`)
      and `stg_album_tracks.sql` (`band, release_group_mbid,
      album_title, album_release_year, recording_mbid, track_title,
      track_title_normalized, track_position`). R2.3 doesn't list
      columns for either; these are what items 12-13 need, with
      `track_title_normalized` carried so the intermediate layer joins
      without re-normalizing. Exclusions are a per-band anti-join
      (`not exists`) against `seed_album_exclusions`, comparing
      `normalize_title()` on BOTH sides per R3.2 — so a curly-vs-straight
      apostrophe can't make an exclusion silently miss.
      `stg_album_tracks` is an inner join to `stg_albums`, so an excluded
      album's tracks go with it. New `dbt/macros/release_year.sql`
      (MusicBrainz dates are `YYYY` / `YYYY-MM` / `YYYY-MM-DD` / NULL;
      takes the first 4 digits when they look like a real year, else
      NULL, never raises) — also used by item 10. `_sources.yml` now
      declares `raw_musicbrainz.albums` and `album_tracks`.
      **Addition beyond the plan, flagged**:
      `dbt/tests/assert_album_exclusions_match_when_band_loaded.sql` —
      fails if an exclusion for a band that IS loaded matches no album
      (MusicBrainz renamed it, or a typo in the seed), which would
      otherwise let the unwanted album flow into the marts with no
      error. It skips bands with no albums loaded, so for
      Muse/A7X/Metallica it is a no-op — not a pass — until their data
      exists.
      **Verified for real**: raw 9 albums → 7 in staging, and the two
      excluded are exactly `Eden Project 2009` and the Manchester
      Academy one; all 78 tracks kept (both excluded albums have 0
      tracks in the raw data); 0 `release_year` mismatches against an
      independent `left(first_release_date, 4)::int`; sample normalized
      track titles read back (`Rock ’n’ Roll Star` → `rock n roll
      star`). Because the real exclusions have no tracks, "an excluded
      album's tracks drop with it" was NOT exercised by real data — so
      I planted a temporary seed row `Oasis / Be Here Now` (12 tracks):
      stg_albums 7 → 6, stg_album_tracks 78 → 66, 0 tracks of that album
      left. Then planted a bogus `Oasis / Nonexistent Album` and the
      guard test went red (1 row). Restored with `dbt seed` (5 seed
      rows, 7 albums, 78 tracks) and the guard test is green again.
- [x] **10. `stg_recordings`** — `dbt/models/staging/stg_recordings.sql`
      (`band, recording_mbid, title, title_normalized,
      first_release_date, release_year`), one row per `(band,
      title_normalized)` via `row_number()`. "Earliest" orders by
      `release_year` (int, NULL last) and only then by the raw date text
      — MusicBrainz dates are mixed precision and text ordering of
      anything unparseable is meaningless — with `recording_mbid` as
      the last tie-break so the result is deterministic. A title that
      normalizes to `''` is dropped instead of collapsed into one bucket
      (1 row in the Oasis data: a `-------------------` recording).
      Two singular tests added:
      `assert_stg_recordings_unique_per_band_title` (composite
      uniqueness; the built-in `unique` is single-column and there's no
      dbt_utils) and `assert_stg_recordings_keeps_earliest_release_year`
      (recomputes the earliest year with a plain `min()` aggregate over
      the raw table, deliberately not reusing the model's window
      function).
      **Verified for real, in three independent ways.** (1) `dbt run` +
      all 7 tests green. (2) Reimplemented the R3.1 rules in Python
      (`re` + `unicodedata`, written from the spec) and compared it with
      the SQL `normalize_title` on every distinct real title: 1,080
      MusicBrainz + 129 setlist.fm = 1,209 titles, **1 disagreement**
      — `Falling Down (「東のエデン」Ver.)`, where the SQL correctly kept
      `エデン` and my *reference* corrupted it to `エテン` (Python's NFKD
      splits kana `デ` into `テ` + a dakuten mark, which I then stripped
      as if it were an accent). The bug was in the reference, not the
      macro; fixed the reference (recompose with NFC) and moved on.
      (3) Recomputed the dedup in Python from the raw rows: 5,596 raw
      recordings → **738 songs**, identical `(band, title)` key set to
      `stg_recordings`, 0 mismatches on the kept release year. Tests
      verified against two injected regressions: earliest → latest
      (the earliest-year test failed with 163 rows while the uniqueness
      test correctly stayed green — the two are independent) and
      `rn = 1` → `rn <= 2` (uniqueness failed with 240 rows, earliest
      with 99); both restored (`diff` identical), 7/7 green.
      **Finding for items 12-13**: 63 of the 738 songs (8.5%) have NO
      dated recording at all, so `release_year` is NULL for them. When
      such a song also has no album match, `int_song_catalog` can only
      give it a NULL year, and a NULL year can't enter an
      `avg_repertoire_age`. R5 says only "matched" performances enter the
      average, and doesn't say what "matched" means for a catalog song
      with no known year — decide this explicitly in item 12/13 (my
      inclination: `is_matched` = resolved to the catalog; the age
      average additionally requires a non-NULL year, and the gap shows up
      in `matched_performances` vs the rows actually averaged).
- [x] **11. Staging schema tests** — `dbt/models/staging/schema.yml`
      (R7.1), plus column/model descriptions: `not_null` on every key and
      flag column, `unique` on `setlist_id` / `release_group_mbid` /
      `recording_mbid`, and `relationships` for entries → setlists and
      tracks → albums. 38 tests total across the project after this
      item. **Severity policy**: columns that are NULL *by design* — the
      date/year columns, since the parsers return NULL instead of
      raising — use `severity: warn` so a bad row is surfaced without
      failing the whole run (a `not_null` that broke the pipeline would
      undo the reason `parse_setlistfm_date` exists). New singular test
      `assert_stg_setlist_entries_unique_key.sql`: the composite key was
      only checked ad hoc in item 8, now it's a permanent guard.
      **Deviations from the spec's literal "not_null and
      accepted_values", stated rather than buried** (also in a comment at
      the top of `schema.yml`): no `accepted_values` on the boolean flags
      (redundant with the column type; `not_null` covers them), none on
      `band` against the 7 names (it would copy `config/bands.yaml` into
      the dbt project, against tech.md's "one versioned place" rule, and
      ingestion writes band names straight from that file so they can't
      drift). The real `accepted_values` candidate, `catalog_source`,
      arrives with `int_song_catalog` in item 12.
      **Verified for real**: `dbt build` → 48 pass + 1 warn, and the
      warn is `not_null_stg_recordings_release_year` with exactly **63**
      rows — the same 63 songs with no dated recording found in item 10,
      so the warn severity is surfacing a known data gap as designed.
      Then proved the tests can actually fail, by mutating raw data
      (checksums of `raw_setlistfm.setlists`/`setlist_entries` identical
      before and after, so restoration was exact): (1) event_date →
      `'garbage'`: `show_date` and `show_year` each WARN with 1 row,
      dbt exit code **0**; (2) `setlistfm_url` → NULL: FAIL, exit code
      **1**; (3) inserted a synthetic medley entry
      `Rock ’n’ Roll Star / Live Forever / ` (tape) into the raw table
      and read it back through the real `stg_setlist_entries`: 2 rows,
      both `position` 9999, `is_medley` true, `medley_part` 1 and 2,
      `is_tape` inherited, the trailing separator did NOT become a third
      part, and all 13 tests in the model's tree passed. **That closes
      part of the item-8 caveat**: the split has now run through the real
      model on a real table row, not only through the fixture — though
      still with a synthetic entry, since no real setlist.fm data with a
      medley exists in this database yet. `relationships` and the
      `unique` tests on raw-PK-backed columns can't be made to fail from
      raw data (FKs/PKs prevent the bad state); they guard against a
      future model change, not against current data.
- [x] **12. `int_song_catalog`** —
      `dbt/models/intermediate/int_song_catalog.sql` (+ `schema.yml`).
      Key `(band, title_normalized)`; columns `band, title_normalized,
      song_title, reference_album, release_year, catalog_source`.
      Precedence **override > album > recording**. `album`: earliest
      studio album containing the song (ties: album title, then mbid),
      year = that album's year. `recording`: no album has it, year =
      earliest recording's. `override`: a `seed_song_overrides` row **with
      an `album_title`** replaces the automatic row and takes its
      album/year from `stg_albums`. **My reading of an underspecified
      rule, flagged**: an override row with a *blank* `album_title` is an
      alias only (raw name → canonical) — it creates no catalog row; item
      13 applies the alias when matching. `catalog_source` gets the real
      `accepted_values` test (the one deferred from item 11). Five new
      tests: unique key, `catalog_source`/`reference_album` consistency,
      and — since the seed is empty and must stay empty (adjustment 5) —
      two seed guards: an override naming an album `stg_albums` doesn't
      have (would silently give a NULL year) and one canonical song given
      two different albums.
      **Verified for real.** (1) Independent Python recomputation from
      the RAW tables: 738 songs (78 `album` + 660 `recording`), same key
      set, **0 rows differing** in (source, album, year); all 63 NULL-year
      songs are `recording`-sourced. (2) Exercised the override path with
      temporary seed rows: `Live Forever → Be Here Now` overrode the
      automatic `Definitely Maybe`/1994 to `override`/`Be Here Now`/1997
      and *replaced* the row (album 77, override 1, total still 738); a
      blank-album alias for Wonderwall changed nothing; an override to a
      nonexistent album gave a NULL-year row and made
      `assert_song_override_albums_exist` FAIL; a contradicting second
      album made `assert_song_overrides_one_album_per_canonical` FAIL;
      and mutating the model to drop the "override beats album" clause
      produced a duplicate key and made the unique test FAIL. All restored
      (`dbt seed` → 0 rows, model `diff` identical, catalog back to
      78/660, full `dbt test` 47 pass + 2 warn).
      **Measured for real, as promised — three findings for you**
      (preliminary: a direct join of non-tape/non-cover entries to the
      catalog; `int_performances` doesn't exist yet):
      1. **NULL year is a non-issue for Oasis**: 11,968 of 11,969
         performances match and **0 of the matched ones lack a year** —
         the 63 no-year songs are obscure recordings never played live.
         The open question (should a matched-but-yearless song count?) is
         moot for this band; it can still bite for the other six, so my
         inclination stands (`is_matched` = resolves to the catalog; the
         age average additionally needs a year) but nothing rides on it
         yet.
      2. **Preliminary match rate 11,968 / 11,969 = 0.9999** (gate:
         0.90); the one miss is `Chipper S.O.B.` (1 play). **Read it with
         care**: 10,400 (86.9%) match through an *album*, 1,568 (13.1%)
         only through a *recording* — and the recording source is every
         release, live take and reissue MusicBrainz has for the artist, so
         "matched to a recording" is a low bar. The spec's gate is about
         matching the catalog as R4.1 defines it (which includes
         recordings), so it passes; but an album-only rate would be 0.869.
         If you want that visible, a second rate in `mart_match_quality`
         is an addition to R6's fixed column list — your call, I have not
         added it.
      3. **Album year vs earliest recording year (spec rule vs project
         brief)**: R4.1 takes the *album's* year when matched, while
         `encore-projeto.md` says "first official release found (album,
         single or EP)". They differ for **8 of 78 album songs** — the
         earliest recording predates the album by 1 year in 7 cases (the
         1993 demos/singles of *Definitely Maybe*, `Go Let It Out`,
         `My Big Mouth`) and by 4 in one (`Let There Be Love`, 2001 vs
         2005). Those 8 songs are **2,361 of the 10,400 album-matched
         plays (22.7%)**, so following the spec biases the average
         repertoire age *low* by roughly 0.2 years. I implemented the
         spec as written; whether the brief's definition should win is a
         methodology decision that isn't mine to make silently.
- [x] **13. `int_performances`** —
      `dbt/models/intermediate/int_performances.sql`. One row per
      performed song (medley parts already split), **tape and cover
      entries excluded** (R4.2), unmatched songs **kept** with
      `is_matched = false` so the match rate is measurable. Columns:
      `setlist_id, band, show_date, show_year, tour_name, set_index,
      position, medley_part, is_encore, is_medley, song_name_raw,
      title_normalized, song_title, reference_album, release_year,
      catalog_source, is_matched, repertoire_age, used_override_alias`.
      Matching key is `normalize_title` of the raw name — unless a seed
      row maps that raw name to a canonical title, in which case the
      **canonical** title is the key (R4.3: overrides beat automatic
      matching). `used_override_alias` records when that happened, so it
      is auditable (an alias-only override leaves no trace in
      `catalog_source`). **`repertoire_age` is deliberately the plain
      SIGNED `show_year - release_year`** — the model makes no decision
      about negative ages; see the pending decision below. Three tests:
      unique key, row count equals stg non-tape/non-cover entries
      (unmatched must stay in), and a contradiction guard
      `assert_song_overrides_unique_raw_name` (one raw name → one
      canonical per band).
      **Verified for real.** (1) Independent Python recomputation **per
      performance** from the raw tables (raw name → normalize →
      catalog recomputed from raw → year → age): 11,969 rows, same key
      set, **0 rows differing** on (matched, source, release_year, age);
      11,968 matched (10,400 `album` + 1,568 `recording`). (2) Alias path
      with temporary seed rows, restored with `dbt seed` each time:
      alias-only `Chipper S.O.B. → Whatever` matched the 1 previously
      unmatched play (matched 11,969, age 2, `used_override_alias`);
      alias *with* an album created an `override` catalog row (year 1997,
      age −2); `Wonderwall → Live Forever` **beat the automatic match**
      for all 550 Wonderwall plays with `matched` unchanged at 11,968;
      two contradictory aliases made the raw-name test FAIL. (3)
      Mutations: dropping the cover exclusion → row-count test FAIL;
      removing the alias `rn = 1` dedupe with two contradictory aliases
      seeded → unique-key test FAIL with **550** rows and row-count FAIL.
      **One mutation was NOT caught, stated plainly**: removing the
      `c.band = r.band` condition from the catalog join went undetected —
      not because the tests are weak but because only one band is loaded,
      so the mutation changes nothing observable. That guard can only be
      exercised once a second band exists; until then the tests do not
      cover cross-band fan-out. Everything restored (model `diff`
      identical, seed 0 rows, full `dbt test` 59 pass + 2 warn).
      **Findings, and a decision I am NOT making (it belongs to item 14
      and to you)**:
      - **89 of 11,968 dated performances (0.74%) have a negative age** —
        a song played in a year before its release year. Most are −1:
        live debuts one year ahead of the record (Definitely Maybe songs
        in 1993, Be Here Now in 1996, Heathen Chemistry in 2001...).
        That is real, legitimate "new material".
      - **Three are matching artifacts**: `Acoustic Song (Live)` (a 1991
        show matched to a 2023 recording → −32) and `Instrumental Jam`
        (1994-98 shows matched to a 2003 recording → −9): generic
        setlist names landing on an arbitrary MusicBrainz recording via
        the `recording` source. `product.md` says jams/solos are excluded
        from catalog KPIs, but setlist.fm gives no flag for them and R4.2
        only excludes tape/cover, so nothing removes them.
      - **Why it matters: R7.3 ("`avg_repertoire_age` is never
        negative") will FAIL on real data** at the band/tour/year grain
        for the earliest years: mean age by show year is −9.00 (1991, 4
        plays), −0.88 (1992, 8) and −0.93 (1993, 40). The overall mean
        is barely touched (6.226 as-is, 6.237 clamped at 0, 6.284
        excluding negatives).
      - **Options for item 14**: (a) clamp each performance's age at 0 —
        a song played before release *is* new material, which is what
        the KPI asks; every matched dated performance stays in the
        average, consistent with R5's "matched, non-tape, non-cover
        performances enter the average"; (b) exclude negative-age
        performances from the average (still counted in `performances`
        and `matched_performances`) — drops real new-material plays and
        biases the mean up; (c) allow negatives and change R7.3 —
        contradicts the spec. **My recommendation is (a)**, but it is a
        methodology choice, so I am stopping before item 14 to ask
        rather than picking. Separately: do you want the jam/generic-name
        artifacts left alone (they are ~3 performances) or handled?
- [x] **14. `mart_repertoire_age`** —
      `dbt/models/analytics/mart_repertoire_age.sql` (+ `schema.yml`),
      a real **table** (`BASE TABLE`), grain band/tour/year, exactly R5's
      12 columns — no `setlist_id`, `show_date`, `venue` or song title.
      **Decisions you made** (recorded here, from the item-13 question):
      negative ages are **clamped to 0** (option a — a song played before
      its release is new material), and the jam/generic-name matching
      artifacts are **left as they are**. Other rules, all stated in the
      model header: only *matched* performances with a *known* age enter
      avg/median/oldest/newest; `performances` and `matched_performances`
      count every non-tape/non-cover performance so `match_rate` is
      honest; no tour → `'Unknown tour'`; performances with an unknown
      `show_year` can't be placed in a year and are left out (the warn on
      `stg_setlists.show_year` surfaces them; 0 for Oasis); `shows` =
      distinct shows with ≥1 performance in the cell. Values are rounded
      to 4 decimals. New singular test on the grain
      (`assert_mart_repertoire_age_unique_grain`) plus `not_null` on the
      key/count columns. The R7.2-7.4 singular tests are items 16-18.
      **A technical trap, avoided and then proven real**: the clamp is a
      `CASE`, not `greatest(age, 0)`, because Postgres `GREATEST` ignores
      NULLs — `greatest(NULL, 0)` is `0`, which would turn "no age" into
      "age 0" and let it into the average.
      **Verified for real.** (1) Independent Python recomputation of the
      whole mart from the raw tables: 36 cells, same key set, **0
      mismatches across all 8 value columns** (shows, performances,
      matched, match_rate, avg, median, oldest, newest — including the
      clamp and the rounding). (2) **Idempotent**: two rebuilds give an
      identical content md5 (excluding `computed_at`) and a later
      `computed_at`; it also returned to the same md5 after the
      experiments below. (3) The clamp is what keeps R7.3 true: without
      it three cells go negative (1991 −9.0000, 1993 −0.9250, 1992
      −0.8750). (4) The GREATEST claim, tested rather than asserted: with
      a temporary alias making one performance matched-but-yearless
      (the catalog song `1994/06/26: Glastonbury Festival`, a recording
      with no date), the `CASE` leaves the 1995 Morning Glory cell's avg
      at 0.4180 while `greatest()` drops it to 0.4173. (5) Reconciled
      totals: `sum(performances)` 11,969 and `sum(matched)` 11,968 equal
      the performance model; `sum(shows)` is 884, not the 891 setlists
      that have any entry, because 7 shows have only tape/cover/blank
      entries (checked directly against raw, not assumed). All restored
      (`dbt seed` → 0 rows, model `diff` identical); full `dbt test`
      68 pass + 2 warn.
      Result for Oasis: 36 cells, 13 distinct tours, 17 `Unknown tour`
      cells holding 413 performances; average age starts ~0 in 1991-94
      (the band is playing its own new songs) and rises through 1998.
- [x] **15. `mart_match_quality`** —
      `dbt/models/analytics/mart_match_quality.sql`, a table, grain
      band/year, exactly R6's 9 columns (counts and rates only). The
      headline metric is `match_rate_by_performance` (weighted by plays,
      per `product.md`); `match_rate_by_title` counts each distinct song
      once and is the harsher view. "Matched" is the same `is_matched`
      flag `mart_repertoire_age` uses. `distinct_songs` counts distinct
      `title_normalized` — the key actually used to join the catalog — so
      two raw names an override maps to one canonical song count once; a
      key that normalizes to `''` is not a title and is not counted (0
      such performances in the Oasis data, so that guard is defensive
      only). `match_rate_by_title` divides by `nullif(distinct_songs, 0)`.
      **I did not add an album-only rate** — that is still your open
      question from item 12.
      Tests: grain uniqueness, an internal-arithmetic guard (matched ≤
      performances, distinct matched ≤ distinct, distinct ≤
      performances), and — new kind — **a cross-mart test**
      `assert_marts_performance_counts_agree`: both marts are built from
      the same performances, so for every (band, year) their performance
      and matched counts must be equal (`mart_repertoire_age` summed over
      tours); a full outer join, so a missing row fails too.
      **Verified for real.** (1) Independent Python recomputation from the
      raw tables: 20 cells, same key set, **0 mismatches across all 6
      value columns**. (2) Idempotent: identical content md5 across
      rebuilds (excluding `computed_at`), and again after the
      experiments. (3) Alias effect on the title counts, checked against
      an independent list: with a temporary `Wonderwall → Live Forever`
      alias `distinct_songs` fell by exactly 1 in exactly the 12 years
      where both raw names were played (1995-98, 2000-02, 2004-06, 2009,
      2025 — the list computed straight from the raw table), unchanged in
      the other 8, with performances/matched untouched. (4) Mutations:
      filtering years < 1995 out of the quality mart → only the
      cross-mart test fails (4 rows, the missing years; internal
      consistency correctly passes); `matched_performances = count(*)+1`
      → internal-consistency **and** cross-mart both fail (20 rows).
      Everything restored (model `diff` identical, seed 0 rows, full
      `dbt test` 77 pass + 2 warn).
      Reading the Oasis result: overall 11,968 / 11,969 = **0.9999** by
      performance. The two views differ visibly only in 1995 — 0.9989 by
      performance vs **0.9706 by title** — because the single unmatched
      song (`Chipper S.O.B.`, 1 play) is 1 of 34 titles that year but 1
      of 940 plays. 2025 has 943 performances, the reunion tour after the
      2009-2025 gap (consistent with Phase 0's 193-month longest pause).
      The by-title rate is the number that would move first if matching
      degraded; the by-performance rate barely can, because a few hit
      songs dominate plays.
- [x] **16. Singular test: no forbidden columns in `analytics`** (R7.2) —
      `dbt/tests/assert_no_forbidden_columns_in_analytics.sql`. It queries
      `information_schema.columns` for schema `analytics` and returns any
      column named `setlist_id`, `show_date`, `venue` or `song_name_raw`.
      It inspects the columns the warehouse really has rather than the
      model SQL, so a future mart or a `select *` is covered too. Limit:
      it matches the four names in the spec exactly; a renamed leak
      (`venue_name`, `event_date`) would pass — the test guards the
      contract, not the intent.
      **Verified for real.** Passes on the current marts. Mutation: added
      `setlist_id`, `show_date`, `venue`, `song_name_raw` as text columns
      to `mart_match_quality` → the test fails with exactly those 4 rows
      (table + column named). Model restored (`git diff` empty), mart
      rebuilt, test green again. The `--store-failures` schema used to
      read the failing rows was dropped afterwards (no `dbt_test__audit`
      left in the DB).
- [x] **17. Singular test: `avg_repertoire_age` never negative** (R7.3) —
      `dbt/tests/assert_avg_repertoire_age_not_negative.sql`. Flags rows
      of `mart_repertoire_age` with a negative average **or median** (the
      median comes from the same clamped ages, so it is the same
      guarantee; the spec names only the average). NULL passes by design.
      **Verified for real.** Green on the current mart. Mutation: removed
      the clamp (`repertoire_age as age`) → the test fails with 4 rows:
      1991, 1992, 1993 (avg −9.0, −0.875, −0.925) and 1999, whose average
      is +0.83 but whose median is −1 — that last row is only caught
      because the median is checked too. Clamp restored (`git diff`
      empty), mart rebuilt, green again. This is the failure that would
      have hit R7.3 on real Oasis data before the clamp decision.
- [x] **18. Singular test: `match_rate` between 0 and 1** (R7.4) —
      `dbt/tests/assert_match_rates_between_0_and_1.sql`. One `union all`
      over all three rate columns: `mart_repertoire_age.match_rate`,
      `mart_match_quality.match_rate_by_performance` and
      `match_rate_by_title` (NULL allowed only on the last, as designed).
      **Verified for real.** Three independent mutations, each restored
      before the next: `match_rate * -1` → fails, 36 rows, attributed to
      `mart_repertoire_age` (min −1.0000, so it covers the lower bound);
      `by_performance * 2` → 20 rows, `mart_match_quality`
      /`match_rate_by_performance` (≈2.0); `by_title * 2` → 20 rows,
      `match_rate_by_title`. All three models `diff`-identical after
      restoring, marts rebuilt, audit schema dropped, test green.
      Full `dbt test` after items 16–18: 80 pass + 2 warn (the same two
      NULL-by-design year warnings); pytest 55 passed.
- [x] **19. `dbt/` copied into the Airflow image** —
      `airflow/Dockerfile`: `COPY dbt/ /opt/airflow/dbt/`, placed **last**
      (after the dbt venv layer) so editing a model never re-downloads
      dbt. Files are root-owned and read-only for the `airflow` user, so
      the image sets `DBT_TARGET_PATH=/tmp/dbt-target`,
      `DBT_LOG_PATH=/tmp/dbt-logs`, `DBT_PROJECT_DIR` and
      `DBT_PROFILES_DIR` (= `/opt/airflow/dbt`) and
      `DBT_SEND_ANONYMOUS_USAGE_STATS=false` as `ENV`, so a bare
      `dbt <cmd>` from a task needs no flags. `.dockerignore` now also
      excludes `dbt/target`, `dbt/logs`, `dbt/.user.yml`,
      `dbt/dbt_packages` so host-generated artifacts never enter the
      image.
      **Verified for real**, without mounting `dbt/` (only what is in the
      image), as uid 50000 on the compose network: the tree is there
      (models, macros, seeds, tests, profiles) with no `target/`,
      `logs/`, `.user.yml` or `.env*`; `dbt debug` → profiles and project
      valid, connection OK; `dbt parse` exits 0, leaves `/opt/airflow/dbt`
      untouched and writes its manifest to `/tmp/dbt-target`. The rebuild
      was fully cached (1.3 s) because nothing else changed. The running
      Airflow containers still use the old image until recreated (done in
      item 20).
- [x] **20. Real `transform` task in `encore_pipeline`** —
      `src/encore/dbt_runner.py` (`run_dbt`, `run_transform`, `DbtError`)
      runs `dbt seed`, `dbt run`, `dbt test` in order via
      `/opt/dbt-venv/bin/dbt`, streaming stdout+stderr line by line
      through `logging` (prefix `[dbt]`) so it appears in the Airflow task
      log live (R8.4). The `transform` task in
      `airflow/dags/encore_pipeline.py` calls it and turns `DbtError` into
      `AirflowFailException` (no retry: same data, same failure). Position
      in the graph and `trigger_rule=all_done` on cleanup/log_run are
      unchanged; `log_run` already treats a missing `transform` result as
      a failed run. The logic sits in `src/` (not in the DAG file) so it
      is unit-testable without Airflow. `DBT_USE_COLORS=false` was added to
      the image `ENV` so logs carry no ANSI codes (0 escape characters
      found in a real task log). `dbt seed` runs on every transform, not
      only when CSVs change (open question 2, as proposed).
      `dbt/README.md` "Running dbt inside Airflow" rewritten (behaviour,
      not-transactional caveat, image needs rebuild after model edits).
      **Verified for real.**
      (1) *Unit tests:* 7 new (62 total). Mutations: ignoring the exit
      code → 2 fail; run before seed → 2 fail; dropping the stderr merge →
      1 fails; all restored.
      (2) *In Airflow, success path, real Oasis data:* dropped the
      `staging`/`intermediate`/`analytics` schemas, then ran only the
      `transform` task → seed 3/3, run 13/13, test 80 pass + 2 warn (the
      same two by-design warnings); both marts came back with **identical
      content checksums** to before the drop (36 and 20 rows), and the raw
      table's physical file was untouched (not truncated).
      (3) *Failure path, single task:* dbt pointed at a nonexistent
      project → task state `failed` with `AirflowFailException`, dbt's own
      error text in the log, `run`/`test` never started.
      (4) *Failure path, whole graph (real run, Oasis, dbt sabotaged):*
      `airflow dags test` → `transform` failed, **`cleanup_raw_setlistfm`
      ran right after and `log_run` last**; afterwards `raw_setlistfm` has
      0 rows in all three tables and `ops.pipeline_runs` has the run as
      `failed` (48 setlist.fm requests). This is R8.3 exercised end to end.
      **Incident while verifying — please read.** My first attempt used
      `airflow tasks test … transform` with `encore_pipeline` *unpaused*
      (left unpaused since spec 01). In Airflow 3 that creates a temporary
      DagRun in the metadata DB and the running scheduler executed its
      real tasks: `truncate_raw_setlistfm_start` **wiped the dev fixture**
      (so my first "rebuild" ran on empty raw data — marts had 0 rows and
      the checksums differed, which is how I noticed), `check_api_budget`,
      and `extract_musicbrainz`. `extract_setlistfm` never ran, so no
      setlist.fm quota was spent. Side effect that remains:
      **`raw_musicbrainz` now also holds Arctic Monkeys** (7 albums, 80
      album tracks, 1,123 recordings, one `loaded_at` for all rows, so it
      looks like an atomic per-band load); the run was interrupted before
      any other band. Those are CC0 MusicBrainz rows in the persistent
      schema, but they are an unplanned change to the dev DB — left in
      place pending your call (harmless for the Oasis marts: rows are keyed
      by band). Fixes: `encore_pipeline` is now **paused** (the compose
      default), the dev fixture was reloaded (958 setlists / 13,170
      entries, 49 requests) and everything above was redone with the DAG
      paused, then `raw_setlistfm` emptied by the failure run's cleanup.
      The pitfall is documented in `dbt/README.md`. Today's setlist.fm
      requests: 49 (fixture reload) + 48 (failure run) = 97 of 1,300.
- [x] **21. `notebooks/01_first_kpi.ipynb`** — 4 code cells, outputs
      cleared (0 outputs, 0 execution counts in the committed file).
      Reads **only** `analytics.mart_repertoire_age` and
      `analytics.mart_match_quality`: `read_analytics()` refuses any table
      outside that whitelist, opens the connection with
      `set_session(readonly=True)` and drops `computed_at`. Connects to
      `127.0.0.1:5435` with `POSTGRES_USER`/`POSTGRES_PASSWORD` from `.env`
      (host/port overridable with `ENCORE_DB_HOST`/`ENCORE_DB_PORT`).
      (1) Line chart, average age by year, one line per band present; a
      year's value is the tour averages weighted by `matched_performances`
      (exact here: 0 matched performances lack an age), and the line
      **breaks over years with no shows** instead of joining across the
      2010–2024 gap. (2) Horizontal bars, average age by tour for `BAND`
      (default Oasis), chronological; multi-year tours are one bar with the
      year span in the label; `Unknown tour` is grey and last, described as
      a pooled bucket, not a real tour. (3) Match-quality tables: totals
      per band and the full band × year table (percent columns). Chart
      style follows the dataviz skill: one fixed colour per band in project
      band order (Oasis = orange even when alone), thin marks, recessive
      grid, text in ink tokens, single series without a legend.
      setlist.fm and MusicBrainz attribution links are in the intro.
      **Verified for real.** Executed a *scratch copy* (outside the repo)
      end to end against the live marts: no errors, both charts rendered
      and inspected by eye. The tour bars (0.3, 1.0, 1.7, 4.5, 4.0, 5.3,
      5.4, 4.0, 5.2, 6.1, 8.3, 30.0, Unknown 1.9) match an independent SQL
      recomputation of the same weighted average from the mart; the tables
      show Oasis 11,969 performances / 11,968 matched (99.99%) over 20
      years. Headline of the chart: the average age climbs from ~0 (1991–94)
      to ~10 in 2007, and the 2025 reunion tour averages **30.0** years —
      an isolated point, since the line does not bridge 2010–2024. Not
      verified: rendering with more than one band (only Oasis is loaded);
      the colour/legend branch for several bands is untested.
- [x] **22. Acceptance run** — `ENCORE_BANDS_FILTER=Oasis` (passed with
      `docker exec -e`, `.env` untouched), full DAG twice with
      `airflow dags test` while `encore_pipeline` stayed **paused** (the
      new CLAUDE.md rule; that command runs the graph in-process and
      needs no unpause). Started from scratch: `raw_setlistfm` at 0 rows
      and the `staging`/`intermediate`/`analytics` schemas dropped, so run
      1 had to build everything.
      | | Run 1 | Run 2 |
      |---|---|---|
      | tasks | all 8 ran, none failed | all 8 ran, none failed |
      | dbt | seed 3/3, run 13/13, test 80 pass + 2 warn | same |
      | `raw_setlistfm` after | 0 / 0 / 0 rows | 0 / 0 / 0 rows |
      | `mart_repertoire_age` / `mart_match_quality` | 36 / 20 rows | 36 / 20 rows |
      | `ops.pipeline_runs` | `success`, 48 setlist.fm requests, 0 MusicBrainz | same |
      | `computed_at` | 17:08:03 | 17:10:17 |
      **Idempotent:** md5 of both marts' content (every column except
      `computed_at`) is identical between run 1 and run 2, and identical to
      the checksums taken before the schemas were dropped in item 20.
      **Match-rate gate (adjustment 5):** Oasis
      `match_rate_by_performance` = 11,968 / 11,969 = **0.9999**, no year
      below 0.90 — far above the 0.90 line, so no unmatched-title list was
      needed and `seed_song_overrides.csv` stays empty (0 rows).
      **All dbt tests pass:** 80 pass, 0 fail, plus the 2 warnings that are
      by design (`release_year` NULL for 63 catalog songs with no dated
      recording; 0 Oasis performances affected). pytest: 62 passed.
      **Notebook** executed (scratch copy, outside the repo) against the
      final marts with no errors; the committed `.ipynb` still has empty
      outputs.
      Quirk noted: for `airflow dags test` runs, `ops.pipeline_runs
      .started_at` is the logical date (00:00) rather than the wall clock,
      so these rows sort below same-day dev-fixture rows; `finished_at` is
      correct. Cosmetic, only affects dev/test runs.
      Data-policy end state: `raw_setlistfm` empty; nothing under
      `analytics` carries setlist ids, dates, venues or titles (item 16's
      test passes); no dev fixture left. setlist.fm requests used today:
      97 (before) + 96 (two runs) = 193 of 1,300.

## Decisions log

- **2026-09-18** — Note on adjustment 3's premise: in this project's
  current setup, `POSTGRES_USER` (`airflow`, used by both dbt and
  `encore.db`) is the official `postgres:16` image's bootstrap role,
  which the image grants `SUPERUSER` by default — so `CREATE EXTENSION`
  actually *would* succeed over the app's normal connection here.
  Implemented the init-script-only approach anyway, per the adjustment:
  it's correct defense-in-depth for a hardened/production setup with a
  restricted app role, and costs nothing to build now.
- **2026-09-18** — `dbt run`/`dbt build`/`dbt seed`/`dbt test` all
  print "Nothing to do" and skip project-level hooks (`on-run-start`)
  when the command's node selection is empty — with zero models/seeds
  so far, there's nothing to validate the hook wiring against except by
  calling the macro directly via `dbt run-operation
  assert_unaccent_extension_exists`. Re-verify the hook fires as part
  of a normal `dbt run` once item 7 (`stg_setlists`) exists.
  **Resolved during item 4**: the first `dbt seed` run had seeds to run
  and the hook fired (`1 of 1 OK hook: encore.on-run-start.0`), and it
  fires on every run since.
- **2026-09-18** — **Interpretation call in `normalize_title` (item 6),
  flagged rather than silently chosen.** R3.1 says to "strip suffixes
  such as remastered, live, demo, edit, and `feat.` segments" while also
  saying it implements "the Phase 0 rules" — but Phase 0's actual rule
  (spec-01 R11.1(c)) deleted *all* bracketed content. Those two
  readings conflict. I implemented the keyword-based one: only a
  `(...)`/`[...]` group, or text after a `" - "`, that contains one of
  `remaster(ed)|live|ao vivo|demo|edit|feat|ft|featuring|single|bonus|
  NNNN version` (whole words) is dropped. Why: deleting every
  parenthesis would turn `(What's the Story) Morning Glory?` into
  `morning glory` and merge `Song (Part 1)` with `Song (Part 2)`. Cost:
  a mismatch like `Morning Glory` (setlist.fm) vs `(What's the Story)
  Morning Glory?` (MusicBrainz) is not fixed by normalization and must
  show up in `mart_match_quality` and be fixed via
  `seed_song_overrides.csv`. The keyword list is Phase 0's list plus
  `demo` and `edit` from the spec. Cheap to flip if the 0.90 gate in
  item 22 says recall is too low — but that is a call for review, per
  the adjustment-5 stop rule, not for me to tune quietly.
- **2026-09-18** — Test-fixture model placement (item 6): put
  `test_normalize_title_cases` in `models/staging/test_fixtures/` so it
  inherits the staging view config instead of adding a fourth layer
  folder to `dbt_project.yml`. Consequence: it builds as a real view,
  `staging.test_normalize_title_cases`, in the database on every full
  `dbt run` (harmless — literal values only).

- **2026-09-21** — Decision on the Arctic Monkeys rows left in
  `raw_musicbrainz` by the item-20 incident: **keep them.** MusicBrainz
  data is persistent by design and will be needed when all bands are
  loaded; it does not affect the Oasis acceptance run because the marts
  start from setlists. Working rule added to `CLAUDE.md`: pause
  `encore_pipeline` before any manual task test and unpause only for a
  deliberate full run.

- **2026-09-21** — **Acceptance.** Item 22 reviewed by the project owner:
  Oasis `match_rate_by_performance` 99.99%; spec 02a accepted and this
  file closed.

- **2026-09-21** — **The two open questions, decided at acceptance.**
  (1) *Album-only match rate:* `match_rate_by_performance` stays the main
  quality metric; `match_rate_by_album` is added to `mart_match_quality`
  as a secondary, informational column. In future era KPIs, songs matched
  to the catalog but not to a studio album form their own category
  "non-album" instead of being dropped. (2) *Song release year:* repertoire
  age uses the song's **first official release year** — the earlier of the
  reference album's year and the recording's first-release-date; the
  reference album stays the basis for era KPIs. A warn-level check lists
  songs whose recording date is more than 2 years before the album year so
  suspicious MusicBrainz dates can be reviewed and fixed through the
  override seed. Both rules are recorded in `docs/context/product.md`;
  implementation is tracked in `docs/specs/spec-02a-followup-progress.md`.
