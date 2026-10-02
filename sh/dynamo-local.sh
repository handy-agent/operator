#!/usr/bin/env bash
# What: Runs DynamoDB Local (official amazon/dynamodb-local image) in Docker for local dev, at
#       http://localhost:8001 (8000 is Operator). Data persists on the Docker volume
#       operator-dynamodb-data across restarts. Commands:
#         start  — start the container if it isn't up (no-op when already running), wait until it answers,
#                  create the Operator table if missing (app/db/dynamo_table.py) and seed it (db/seed/)
#         stop   — stop the container (data kept)
#         reset  — delete the container and its volume (ALL local DynamoDB data), then start fresh
#         status — show whether it's running
# When: start runs on every app start (sh/run.sh); the others by hand.
# Called by: sh/run.sh, sh/sim.sh (start); developer / Claude by hand. Usage: sh/dynamo-local.sh start|stop|reset|status
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
CONTAINER=operator-dynamodb
VOLUME=operator-dynamodb-data
IMAGE=amazon/dynamodb-local:latest
PORT=8001

is_running() {
  [ "$(docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null)" = "true" ]
}

exists() {
  docker inspect "$CONTAINER" >/dev/null 2>&1
}

wait_ready() {
  for _ in $(seq 1 20); do
    # Any HTTP answer (DynamoDB returns 400 on a bare GET) means it's up.
    if curl -s -o /dev/null "http://localhost:$PORT"; then
      echo "DynamoDB Local up: http://localhost:$PORT"
      return 0
    fi
    sleep 0.5
  done
  echo "DynamoDB Local did not answer on port $PORT" >&2
  return 1
}

# Creates the table if missing; a fresh table also gets the seed data (sh/dynamo-seed.sh).
create_table() {
  local out
  out="$(DYNAMODB_ENDPOINT_URL="http://localhost:$PORT" .venv/bin/python -m app.db.dynamo_table create)"
  echo "$out"
  if [[ "$out" == *created ]]; then
    DYNAMODB_ENDPOINT_URL="http://localhost:$PORT" DB_BACKEND=dynamodb sh/dynamo-seed.sh
  fi
}

start() {
  if is_running; then
    echo "DynamoDB Local already running: http://localhost:$PORT"
    create_table
    return 0
  fi
  if exists; then
    docker start "$CONTAINER" >/dev/null
  else
    # Runs as root so it can write to the fresh named volume (root-owned on creation). Local dev only.
    docker run -d --name "$CONTAINER" --user root \
      -p "$PORT:8000" \
      -v "$VOLUME:/data" \
      "$IMAGE" -jar DynamoDBLocal.jar -sharedDb -dbPath /data >/dev/null
  fi
  wait_ready
  create_table
}

stop() {
  if is_running; then
    docker stop "$CONTAINER" >/dev/null
  fi
  echo "DynamoDB Local stopped"
}

reset() {
  if exists; then
    docker rm -f "$CONTAINER" >/dev/null
  fi
  docker volume rm -f "$VOLUME" >/dev/null
  echo "DynamoDB Local data deleted"
  start
}

status() {
  if is_running; then
    echo "running: http://localhost:$PORT (volume $VOLUME)"
  else
    echo "not running"
  fi
}

case "${1:-}" in
  start) start ;;
  stop) stop ;;
  reset) reset ;;
  status) status ;;
  *) echo "Usage: $0 start|stop|reset|status" >&2; exit 1 ;;
esac
