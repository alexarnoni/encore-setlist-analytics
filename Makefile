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

.PHONY: up down ps logs

up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

ps:
	$(COMPOSE) ps

logs:
	$(COMPOSE) logs -f
