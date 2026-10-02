#!/usr/bin/env bash
# What: One-command local startup. Makes sure the tunnel service is running (sh/tunnel-service.sh),
#       then opens a new GNOME Terminal window running Operator (sh/run.sh) so its logs are visible live.
#       Closing that window stops Operator; the tunnel keeps running.
# When: Run from anywhere when you want Operator up for local/webhook testing.
# Called by: developer / Claude, by hand. Usage: sh/start.sh [port]
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${1:-8000}"

if systemctl --user is-active --quiet operator-tunnel; then
  "$DIR/tunnel-service.sh" url
else
  "$DIR/tunnel-service.sh" start "$PORT"
fi

gnome-terminal --title="Operator :$PORT" -- bash -c "\"$DIR/run.sh\" $PORT; echo; read -rp 'Operator stopped. Press Enter to close.'"
