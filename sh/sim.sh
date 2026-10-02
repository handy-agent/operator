#!/usr/bin/env bash
# What: Two-window simulator for one new simulated lead. Opens "Chat" (lead messages, /out for your
#       own replies) and "Notes" (notes to you + your instructions to the agent, /resume) GNOME Terminal
#       windows sharing one conversation under sim/runs/<id>/. Nothing is sent to Thumbtack.
#       --telegram <account_id>: Telegram in place of the Notes window. The sim lead belongs to that account;
#       notes go to its connected Telegram chats (sh/connect-telegram.sh), answered there. Needs
#       TELEGRAM_BOT_TOKEN in .env and Operator stopped. The window shows its log.
#       Starts DynamoDB Local first if it isn't up (sh/dynamo-local.sh start).
# When: Run manually to test Operator end to end, including your approvals.
# Called by: developer / Claude, by hand. Usage: sh/sim.sh [--telegram <account_id>]
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
sh/dynamo-local.sh start
SIM_ID="sim-$(date +%Y%m%d-%H%M%S)"
PY="$PWD/.venv/bin/python"

NOTES_MODULE=sim.notes
NOTES_TITLE=Notes
ACCOUNT_ID=""
if [[ "${1:-}" == "--telegram" ]]; then
  ACCOUNT_ID="${2:?usage: sh/sim.sh --telegram <account_id>}"
  NOTES_MODULE=sim.telegram
  NOTES_TITLE=Telegram
fi

gnome-terminal --title="$NOTES_TITLE — $SIM_ID" --working-directory="$PWD" -- bash -c \
  "\"$PY\" -m $NOTES_MODULE $SIM_ID; echo; read -rp 'Ended. Press Enter to close.'"
gnome-terminal --title="Chat — $SIM_ID" --working-directory="$PWD" -- bash -c \
  "\"$PY\" -m sim.chat $SIM_ID $ACCOUNT_ID; echo; read -rp 'Ended. Press Enter to close.'"
echo "Opened $SIM_ID"
