# Source me:  source scripts/spec03/env.sh
#
# Isolated development environment for spec 03. Everything here talks to its
# OWN Postgres container (`spec03-postgres`, on its own Docker network), never
# to the real `encore` database and never to the running Encore stack: the
# real `postgres` service is not even reachable from the containers started by
# these helpers.
#
# Uses the Windows Docker CLI path from Git Bash; harmless elsewhere.

export PATH="/c/Users/alexc/AppData/Local/Programs/DockerDesktop/resources/bin:$PATH"

S3_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
set -a; source "$S3_ROOT/.env"; set +a          # POSTGRES_USER / POSTGRES_PASSWORD only

S3_CONTAINER=spec03-postgres
S3_NETWORK=spec03-net
S3_VOLUME=spec03-pgdata
S3_HOST_PORT=5446                                # published on 127.0.0.1 only
# Image used to run dbt and Python: the spec-03 branch image (has lifelines). It
# is only ever `docker run` from; `encore-airflow:3.3.2` is never rebuilt or retagged.
S3_IMAGE="${S3_IMAGE:-encore-airflow:spec-03}"

# psql inside the spec-03 Postgres.
s3psql() { docker exec -i "$S3_CONTAINER" psql -U "$POSTGRES_USER" -d encore -v ON_ERROR_STOP=1 "$@"; }

# Environment for a throwaway container attached to the spec-03 network only.
_s3_run() {
  MSYS_NO_PATHCONV=1 docker run --rm --network "$S3_NETWORK" \
    -e POSTGRES_HOST="$S3_CONTAINER" -e POSTGRES_PORT=5432 \
    -e POSTGRES_USER -e POSTGRES_PASSWORD \
    -e DBT_TARGET_PATH=/tmp/dbt-target -e DBT_LOG_PATH=/tmp/dbt-logs \
    -e DBT_SEND_ANONYMOUS_USAGE_STATS=false -e DBT_USE_COLORS=false \
    -v "$S3_ROOT/dbt:/opt/airflow/dbt" \
    -v "$S3_ROOT/src:/opt/airflow/src:ro" \
    -v "$S3_ROOT/scripts:/opt/airflow/scripts:ro" \
    -v "$S3_ROOT/tests:/opt/airflow/tests:ro" \
    "$@"
}

# dbt against the spec-03 database:  s3dbt seed --full-refresh | run | test ...
s3dbt() {
  _s3_run --entrypoint /opt/dbt-venv/bin/dbt "$S3_IMAGE" "$@" \
    --project-dir /opt/airflow/dbt --profiles-dir /opt/airflow/dbt
}

# Python with the project's src/ on the path, against the spec-03 database.
s3py() { _s3_run --entrypoint python -e PYTHONPATH=/opt/airflow/src:/opt/airflow "$S3_IMAGE" "$@"; }

# Point HOST-side Python (pytest, notebooks) at the spec-03 database.
s3hostenv() { export POSTGRES_HOST=localhost POSTGRES_PORT="$S3_HOST_PORT"; }
