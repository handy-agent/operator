#!/usr/bin/env bash
# What: Opens a Cloudflare quick tunnel (public HTTPS URL, no account) to the local Operator server,
#       so Thumbtack webhooks can reach http://127.0.0.1:<port>/webhooks/thumbtack.
#       The URL is random and changes every run — re-register it with the provider each time.
# When: Run from operator/ to test webhooks locally. Start order vs. Operator (uvicorn, port 8000) does not matter —
#       requests return 502 until Operator is up. Operator can restart freely; the tunnel URL stays.
# Called by: developer / Claude, by hand. Usage: sh/tunnel.sh [port]
set -euo pipefail

PORT="${1:-8000}"
CLOUDFLARED="$(command -v cloudflared || echo "$HOME/.local/bin/cloudflared")"

if [ ! -x "$CLOUDFLARED" ]; then
  echo "cloudflared not found. Run sh/install-cloudflared.sh first." >&2
  exit 1
fi

echo "Tunneling to http://127.0.0.1:$PORT"
echo "Webhook URL = <trycloudflare URL printed below>/webhooks/thumbtack"
exec "$CLOUDFLARED" tunnel --no-autoupdate --url "http://127.0.0.1:$PORT"
