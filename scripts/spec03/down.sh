#!/usr/bin/env bash
# Remove the isolated spec-03 Postgres, its volume and its network.
# Touches only the `spec03-*` resources; the .spec03-local/mb.sql cache stays.
set -uo pipefail
source "$(dirname "$0")/env.sh"
docker rm -f "$S3_CONTAINER" >/dev/null 2>&1
docker volume rm "$S3_VOLUME" >/dev/null 2>&1
docker network rm "$S3_NETWORK" >/dev/null 2>&1
echo "spec03 environment removed"
exit 0
