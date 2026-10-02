#!/usr/bin/env bash
# What: Emulates connecting a customer to Operator on Telegram: creates the account (if new) and prints a
#       one-time link. The customer opens it on their phone and taps Start — their chat is linked.
#       Needs TELEGRAM_BOT_TOKEN (the product bot) in .env and Operator or `sh/sim.sh --telegram` running
#       to receive the Start.
# When: Once per customer (or per extra phone of the same customer).
# Called by: developer / Claude, by hand. Usage: sh/connect-telegram.sh <account_id> ["Business name"]
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
exec .venv/bin/python -m app.connect "$@"
