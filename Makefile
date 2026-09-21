# Convenience wrapper around docker compose.
#
# infra/docker-compose.yml resolves its own ${VAR} interpolation
# (including its required-variable checks) against a .env file in the
# compose file's own directory (infra/) by default, not against this
# repo root where the real .env lives — so a bare `docker compose up`
# fails with "variable is missing a value" unless --env-file is passed
# explicitly every time. These targets do that consistently, so nobody
# has to remember or retype the full invocation.

COMPOSE := docker compose -f infra/docker-compose.yml --env-file .env
# Local development only: also bind-mounts ./dbt into the Airflow containers.
COMPOSE_DEV := docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml --env-file .env

# Commit of the dbt project, baked into the image at build time and logged by
# the transform task (`-dirty` = uncommitted changes under dbt/). Empty when
# git is unavailable; compose then falls back to "unknown".
DBT_GIT_COMMIT := $(shell git log -1 --format=%h -- dbt 2>/dev/null)$(shell git diff --quiet HEAD -- dbt 2>/dev/null || echo -dirty)
export DBT_GIT_COMMIT

.PHONY: up up-dev build down ps logs

up:
	$(COMPOSE) up -d

# Same as `up`, plus ./dbt mounted read-only so dbt changes need no rebuild.
up-dev:
	$(COMPOSE_DEV) up -d

# Rebuild the Airflow image (bakes the current dbt/ and its commit hash).
build:
	$(COMPOSE) build

down:
	$(COMPOSE) down

ps:
	$(COMPOSE) ps

logs:
	$(COMPOSE) logs -f
