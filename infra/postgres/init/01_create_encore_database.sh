#!/bin/bash
# Runs only when the postgres-db-volume is empty (official Postgres image
# behavior for /docker-entrypoint-initdb.d). Creates the `encore` database
# alongside the `airflow` database created by POSTGRES_DB. Schema creation
# inside `encore` (raw_setlistfm, raw_musicbrainz, staging, intermediate,
# analytics, ops) is handled separately so it can also run on demand
# against an existing database — see docs/specs/spec-01-progress.md item 6.
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-EOSQL
    SELECT 'CREATE DATABASE encore OWNER ' || quote_ident('$POSTGRES_USER')
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'encore')\gexec
EOSQL
