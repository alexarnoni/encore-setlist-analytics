# Tech stack and constraints

## Stack

- Python 3.12
- PostgreSQL 16 (dedicated instance for Encore, databases `encore` and `airflow`)
- Apache Airflow with LocalExecutor (custom image extending the official one, with dbt-postgres installed)
- dbt Core with dbt-postgres
- pandas and lifelines for analysis
- FastAPI for the public API
- Static frontend on Cloudflare Pages (later spec)
- Docker Compose for all services

## Deployment target

- Oracle Cloud VM, ARM64 (aarch64), 4 cores, 23 GB RAM, Ubuntu 24.04
- Every Docker image must support linux/arm64
- Nginx runs on the host and is the only public entry point
- Project directory on the VM: /opt/encore

## Ports (all bound to 127.0.0.1, never 0.0.0.0)

| Service | Host port |
|---|---|
| Encore API | 8003 |
| Airflow webserver | 8080 (accessed through SSH tunnel only) |
| PostgreSQL | 5435 |

Ports 8000, 8001, 8002, 5433 and 5434 belong to other projects on the same VM.

## External APIs

### setlist.fm
- Base URL: https://api.setlist.fm/rest/1.0
- Headers: `x-api-key`, `Accept: application/json`
- Limits: 2 requests/second, 1,440 requests/day. Use a 1 second pause between real calls.
- Artist setlists endpoint returns 20 setlists per page. Full load for all 7 bands is about 475 requests.

### MusicBrainz
- Base URL: https://musicbrainz.org/ws/2, parameter `fmt=json`
- User-Agent required: `Encore/0.1 (alexandre.anf@gmail.com)`
- Max 1 request/second

### Both
- Retry on 429 and 503 with exponential backoff (2s, 4s, 8s), max 3 attempts
- Count real requests per run and log them

## Conventions

- Secrets only in `.env` (never committed). Provide `.env.example`.
- Code, comments, docs and commit messages in English.
- Type hints and docstrings in Python code.
- Structured logging (no bare prints in pipeline code).
- Configuration through environment variables, not hardcoded values.
- Band list and manual corrections live in versioned config or dbt seeds, not in code.
