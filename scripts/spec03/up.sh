#!/usr/bin/env bash
# Start (or reset) the isolated spec-03 Postgres and load what dbt needs:
#   * database `encore` with the `unaccent` extension and the layer schemas;
#   * the real MusicBrainz tables (persistent CC0 data), copied read-only from
#     the real database through a throwaway pg_dump container. The copy is
#     cached in .spec03-local/mb.sql (gitignored), so it is dumped only once;
#   * empty raw_setlistfm tables, created by the project's own DDL.
# No setlist.fm data is ever loaded here except the synthetic histories.
#
# Usage: scripts/spec03/up.sh          (idempotent; keeps existing data)
#        scripts/spec03/up.sh --reset  (drops the volume first)
set -euo pipefail
source "$(dirname "$0")/env.sh"

if [ "${1:-}" = "--reset" ]; then "$(dirname "$0")/down.sh"; fi

docker network inspect "$S3_NETWORK" >/dev/null 2>&1 || docker network create "$S3_NETWORK" >/dev/null
docker volume inspect "$S3_VOLUME" >/dev/null 2>&1 || docker volume create "$S3_VOLUME" >/dev/null

if ! docker ps -a --format '{{.Names}}' | grep -qx "$S3_CONTAINER"; then
  docker run -d --name "$S3_CONTAINER" --network "$S3_NETWORK" \
    -p "127.0.0.1:${S3_HOST_PORT}:5432" -v "$S3_VOLUME:/var/lib/postgresql/data" \
    -e POSTGRES_USER -e POSTGRES_PASSWORD -e POSTGRES_DB=encore postgres:16 >/dev/null
elif ! docker ps --format '{{.Names}}' | grep -qx "$S3_CONTAINER"; then
  docker start "$S3_CONTAINER" >/dev/null
fi

for _ in $(seq 1 40); do
  docker exec "$S3_CONTAINER" pg_isready -U "$POSTGRES_USER" -d encore >/dev/null 2>&1 && break
  sleep 1
done

s3psql -q -c "create extension if not exists unaccent" \
          -c "create schema if not exists raw_setlistfm" \
          -c "create schema if not exists staging" \
          -c "create schema if not exists intermediate" \
          -c "create schema if not exists analytics" >/dev/null

# MusicBrainz copy (skipped when already loaded).
if [ "$(s3psql -tAc "select count(*) from information_schema.tables where table_schema='raw_musicbrainz'")" = "0" ]; then
  mkdir -p "$S3_ROOT/.spec03-local"
  if [ ! -s "$S3_ROOT/.spec03-local/mb.sql" ]; then
    echo "dumping raw_musicbrainz from the real database (read-only)..."
    docker run --rm --network infra_default -e PGPASSWORD="$POSTGRES_PASSWORD" postgres:16 \
      pg_dump -h postgres -U "$POSTGRES_USER" -d encore -n raw_musicbrainz > "$S3_ROOT/.spec03-local/mb.sql"
  fi
  s3psql -q < "$S3_ROOT/.spec03-local/mb.sql" >/dev/null
fi

# Empty raw_setlistfm tables from the project's own DDL.
s3py -c "
from encore.db import get_connection
from encore.ingestion import setlistfm
conn = get_connection(); setlistfm.ensure_tables(conn); conn.close()"

echo "spec03-postgres ready on 127.0.0.1:${S3_HOST_PORT}: $(s3psql -tAc "select count(*) from raw_musicbrainz.albums") albums, $(s3psql -tAc "select count(*) from raw_musicbrainz.recordings") recordings"
