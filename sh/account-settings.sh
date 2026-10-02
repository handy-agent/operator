#!/usr/bin/env bash
# What: Shows a customer's settings (reply timing, first-reply delay, hold time, alarm, session warmth),
#       or changes them while Operator runs — no restart needed. key=default goes back to the default.
# When: Whenever a customer's timing or alerting should change.
# Called by: developer / Claude, by hand. Usage: sh/account-settings.sh <account_id> [key=value ...]
#   e.g. sh/account-settings.sh atx alarm_for_seconds=180 first_reply_immediate=off
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
exec .venv/bin/python -m app.settings_cli "$@"
