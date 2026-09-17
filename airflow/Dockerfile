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
