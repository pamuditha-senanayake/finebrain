#!/usr/bin/env bash
# dev_up.sh: start all local infra in one go and wait until every service is healthy.
# Uses: backend/infra/compose.yaml. Stop everything with: docker compose -f backend/infra/compose.yaml down
# The backend (8000) and frontend (3000) servers start separately, from .claude/launch.json.
set -euo pipefail

# Run from anywhere: find the compose file next to this script
COMPOSE_FILE="$(cd "$(dirname "$0")/../infra" && pwd)/compose.yaml"

# Start and wait for health checks
docker compose -f "$COMPOSE_FILE" up -d --wait

# Show where everything lives
cat <<'PORTS'

Local infra is up:
  Postgres            localhost:5433
  Redpanda (Kafka)    localhost:9092
  Redpanda console    http://localhost:8080
  Schema registry     localhost:8081
  Valkey              localhost:6379
  S3 (SeaweedFS)      http://localhost:9000
PORTS
