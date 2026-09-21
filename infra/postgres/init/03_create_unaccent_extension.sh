#!/bin/bash
# Runs only when the postgres-db-volume is empty (official Postgres
# image behavior for /docker-entrypoint-initdb.d), after 02_create_schemas.sh.
#
# CREATE EXTENSION requires superuser, which the app's runtime role
# (POSTGRES_USER, used by dbt and encore.db) does not have — this is
# the only place the unaccent extension gets created. dbt's
# on-run-start hook (dbt/macros/assert_unaccent_extension_exists.sql)
# only checks it exists and fails with a clear message if it doesn't,
# so a missing extension (e.g. a database that predates this script) is
# caught immediately at the start of `dbt run`, not mid-way through the
# first model that calls normalize_title().
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname encore <<-EOSQL
    CREATE EXTENSION IF NOT EXISTS unaccent;
EOSQL
