#!/usr/bin/env bash
# What: Runs the named Cloudflare tunnel "handyagent-local" to the local Operator server.
#       Stable URL https://local.handyagent.dev — same on every run, register it with Thumbtack once.
#       (sh/tunnel.sh is the old quick tunnel with a random URL; kept as a fallback.)
# When: Run from operator/ for local webhook testing. Needs sh/local-tunnel-setup.sh done once.
#       Start order vs. Operator does not matter — requests return 502 until Operator is up.
# Called by: sh/tunnel-service.sh (systemd user service), or developer / Claude by hand. Usage: sh/local-tunnel.sh [port]
set -euo pipefail

TUNNEL=handyagent-local
PORT="${1:-8000}"
CLOUDFLARED="$(command -v cloudflared || echo "$HOME/.local/bin/cloudflared")"

if [ ! -x "$CLOUDFLARED" ]; then
  echo "cloudflared not found. Run sh/install-cloudflared.sh first." >&2
  exit 1
fi

echo "Tunneling https://local.handyagent.dev -> http://127.0.0.1:$PORT"
exec "$CLOUDFLARED" tunnel --no-autoupdate run --url "http://127.0.0.1:$PORT" "$TUNNEL"
