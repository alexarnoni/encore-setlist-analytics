# Encore dbt project

> Grows task by task with spec-02a. See
> [docs/specs/spec-02a-progress.md](../docs/specs/spec-02a-progress.md)
> for the detailed build log.

## Local development data

`raw_setlistfm` is ephemeral by data policy (see
[docs/context/product.md](../docs/context/product.md)) — the real
pipeline truncates it at the end of every run, so there's normally
nothing to develop dbt models against between runs.

For local dbt development, load a one-off, real (not synthetic) fixture
for a single band instead of running the full pipeline repeatedly:

```bash
PYTHONPATH=src POSTGRES_HOST=localhost POSTGRES_PORT=5435 \
    python scripts/load_dev_fixture.py
```

This loads Oasis into `raw_setlistfm` and `raw_musicbrainz` directly,
bypassing `encore_pipeline` and its `cleanup_raw_setlistfm` task, and
records the load timestamp in `ops.pipeline_runs` (`status =
'dev-fixture'`) so it's visible and distinguishable from a real run.

**This data is TEMPORARY.** Do not leave it in the database between
work sessions — truncate `raw_setlistfm` when you're done for the day:

```bash
PYTHONPATH=src POSTGRES_HOST=localhost POSTGRES_PORT=5435 python -c "
from encore.db import get_connection
from encore.ingestion.setlistfm import truncate_all
truncate_all(get_connection())
"
```

(`raw_musicbrainz` is persistent by design — see
[docs/context/structure.md](../docs/context/structure.md) — so it's
fine to leave the MusicBrainz half of the fixture in place.)
