#!/bin/bash
# Runs only when the postgres-db-volume is empty (official Postgres image
# behavior for /docker-entrypoint-initdb.d), after 01_create_encore_database.sh
# has created the `encore` database. Explicitly targets --dbname encore,
# since init scripts otherwise connect to $POSTGRES_DB (the airflow
# metadata database) by default.
#
# The same schemas can be (re)created on demand against an existing
# database — e.g. after this container's first boot — via:
#   python -m encore.db
# (see src/encore/db.py, README.md "Database schema bootstrap").
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname encore <<-EOSQL
    CREATE SCHEMA IF NOT EXISTS raw_setlistfm;
    CREATE SCHEMA IF NOT EXISTS raw_musicbrainz;
    CREATE SCHEMA IF NOT EXISTS staging;
    CREATE SCHEMA IF NOT EXISTS intermediate;
    CREATE SCHEMA IF NOT EXISTS analytics;
    CREATE SCHEMA IF NOT EXISTS ops;
EOSQL
