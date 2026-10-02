#!/usr/bin/env bash
# What: Starts DynamoDB Local if it isn't up (sh/dynamo-local.sh start), then the Operator FastAPI app
#       locally (uvicorn, 127.0.0.1, port 8000 by default) with auto-reload.
# When: Run from operator/ for local dev and webhook testing (pair with sh/tunnel-service.sh).
# Called by: sh/start.sh; developer / Claude, by hand. Usage: sh/run.sh [port]
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
sh/dynamo-local.sh start
exec .venv/bin/uvicorn app.main:app --reload --env-file .env --host 127.0.0.1 --port "${1:-8000}"
