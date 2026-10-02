#!/usr/bin/env bash
# What: Local chat simulator — you type as the customer, the real Operator agent replies in the terminal.
#       Type /quit or press Ctrl+D to end (empty lines are ignored).
#       Nothing is sent to Thumbtack. Each run creates a new "sim-<timestamp>" lead in the record store.
#       Starts DynamoDB Local first if it isn't up (sh/dynamo-local.sh start).
# When: Run manually to see how Operator handles a conversation before going live.
# Called by: developer / Claude, by hand. Usage: sh/chat.sh
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
sh/dynamo-local.sh start
exec .venv/bin/python -m sim.single
