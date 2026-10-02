#!/usr/bin/env bash
# What: Runs the live estimate scenarios (approve as suggested, the owner changes price, the owner wants photos
#       first, lead haggles) against the real agent. Uses Claude, takes a few minutes. Nothing is sent
#       to Thumbtack; scenario records are cleaned up afterwards.
# When: By hand after changing prompts or estimate logic.
# Called by: developer / Claude, by hand. Usage: sh/live-estimate-scenarios.sh
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
exec .venv/bin/python -m tests.live.estimate_scenarios
