# Custom Airflow image for Encore: official image + project ingestion code
# + dbt in its own virtualenv.
#
# Base image is the official multi-arch apache/airflow build, so this
# Dockerfile needs no buildx/multi-platform setup — a native `docker build`
# on the target machine (x86 locally, arm64 on the Oracle VM) produces a
# working image for that machine's architecture.
FROM apache/airflow:3.3.2-python3.12

# --- Project ingestion code, installed into Airflow's own environment ---
# Pinned to the Airflow release's own constraints file so provider
# dependencies already resolved by the base image are not disturbed.
ARG AIRFLOW_CONSTRAINTS_URL=https://raw.githubusercontent.com/apache/airflow/constraints-3.3.2/constraints-3.12.txt

USER airflow

COPY airflow/requirements.txt /opt/airflow/requirements.txt
RUN pip install --no-cache-dir \
    --constraint "${AIRFLOW_CONSTRAINTS_URL}" \
    -r /opt/airflow/requirements.txt

COPY src/ /opt/airflow/src/
COPY config/ /opt/airflow/config-data/
ENV PYTHONPATH="/opt/airflow/src"
# encore.config.load_bands() otherwise assumes config/ sits next to src/
# (true for local dev and the notebook), which doesn't hold here: config/
# is copied to config-data/ specifically to avoid colliding with
# Airflow's own /opt/airflow/config directory.
ENV ENCORE_BANDS_FILE="/opt/airflow/config-data/bands.yaml"

# --- dbt, isolated in its own venv ---
# dbt-core/dbt-postgres pin their own dependency versions (e.g. Jinja2,
# click) which can conflict with the versions Airflow's providers need.
# A separate venv keeps the two dependency sets from fighting each other.
# It is intentionally NOT added to PATH: call it via its full path
# (/opt/dbt-venv/bin/dbt) so it never shadows Airflow's own `python`/`pip`.
ARG DBT_CORE_VERSION=1.12.3
ARG DBT_POSTGRES_VERSION=1.11.0
# Matches the default AIRFLOW_UID in infra/docker-compose.yml / .env.example.
ARG AIRFLOW_UID=50000

USER root
RUN python -m venv /opt/dbt-venv \
    && /opt/dbt-venv/bin/pip install --no-cache-dir \
        "dbt-core==${DBT_CORE_VERSION}" \
        "dbt-postgres==${DBT_POSTGRES_VERSION}" \
    && chown -R "${AIRFLOW_UID:-50000}:0" /opt/dbt-venv
ENV DBT_VENV=/opt/dbt-venv

USER airflow

# --- dbt project ---
# Last on purpose: it changes far more often than anything above, and
# putting it after the venv layer keeps a model edit from rebuilding
# (re-downloading) dbt itself. Root-owned and read-only for the airflow
# user, so everything dbt writes goes to /tmp instead of the project dir.
COPY dbt/ /opt/airflow/dbt/
# Commit of the dbt project baked into this image, logged at the start of
# every transform run. `unknown` unless passed at build time
# (`make build`, or `DBT_GIT_COMMIT=$(git log -1 --format=%h -- dbt)`).
ARG DBT_GIT_COMMIT=unknown
ENV ENCORE_DBT_COMMIT=${DBT_GIT_COMMIT} \
    DBT_PROJECT_DIR=/opt/airflow/dbt \
    DBT_PROFILES_DIR=/opt/airflow/dbt \
    DBT_TARGET_PATH=/tmp/dbt-target \
    DBT_LOG_PATH=/tmp/dbt-logs \
    DBT_SEND_ANONYMOUS_USAGE_STATS=false \
    DBT_USE_COLORS=false
