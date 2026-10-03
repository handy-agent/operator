#!/usr/bin/env bash
# What: Loads the seed files in db/seed/ (pricing catalog: services, subservices, multipliers) into
#       DynamoDB (app/db/seed.py). Each kind ends up exactly like the seed files; safe to rerun.
#       Which DynamoDB: from the environment / .env — locally DynamoDB Local (DYNAMODB_ENDPOINT_URL);
#       for a stage, the deploy sets DYNAMODB_TABLE + AWS credentials and leaves the endpoint empty.
# When: Automatically when sh/dynamo-local.sh creates a fresh local table; by hand after the seed files
#       change (e.g. sh/import-thumbtack-prices.sh); per AWS stage on its first init (operator-deploy).
# Called by: sh/dynamo-local.sh; developer / Claude by hand; the deploy (operator-deploy). Usage: sh/dynamo-seed.sh
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
exec .venv/bin/python -m app.db.seed
