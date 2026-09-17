# Repository structure

```
encore-setlist-analytics/
├── airflow/
│   ├── dags/                 # Airflow DAGs
│   └── Dockerfile            # Airflow image with dbt-postgres
├── config/
│   └── bands.yaml            # Bands in scope (name, MBID)
├── dbt/                      # dbt project (later spec)
│   ├── models/
│   │   ├── staging/
│   │   ├── intermediate/
│   │   └── marts/
│   └── seeds/                # Manual corrections (album exclusions, dates, song mapping)
├── docs/
│   ├── context/              # Product, tech and structure context
│   ├── specs/                # Implementation specs
│   └── encore-projeto.md     # Project brief
├── infra/
│   ├── docker-compose.yml
│   └── postgres/init/        # Database and schema creation scripts
├── notebooks/
│   └── 00_validacao.ipynb    # Phase 0 validation (outputs always cleared)
├── src/
│   └── encore/
│       ├── clients/          # setlist.fm and MusicBrainz clients
│       ├── ingestion/        # Extraction and loading logic
│       └── db.py             # Database connection helpers
├── tests/
├── CLAUDE.md                 # Claude Code instructions
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

## Database schemas (database `encore`)

| Schema | Content | Lifetime |
|---|---|---|
| `raw_setlistfm` | Raw setlist.fm data | Ephemeral: truncated at the end of every run |
| `raw_musicbrainz` | Raw MusicBrainz data | Persistent |
| `staging`, `intermediate` | dbt models over raw data | Views only, never tables |
| `analytics` | Aggregated marts | Persistent |
| `ops` | Run log (run id, timestamps, request counts, row counts, status) | Persistent |

## Rules

- Nothing under `analytics` may contain per-show or per-setlist rows derived from setlist.fm.
- `src/clients.py` from Phase 0 is the starting point for `src/encore/clients/`.
