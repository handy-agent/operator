#!/usr/bin/env bash
# What: One-time setup of the named Cloudflare tunnel for local dev: creates tunnel "handyagent-local"
#       (credentials in ~/.cloudflared/) and points DNS local.handyagent.dev at it. Safe to re-run —
#       skips what already exists.
# When: Once per machine, after `cloudflared tunnel login` (the owner approves handyagent.dev in the browser).
# Called by: developer / Claude, by hand. Usage: sh/local-tunnel-setup.sh
set -euo pipefail

TUNNEL=handyagent-local
HOSTNAME=local.handyagent.dev
CLOUDFLARED="$(command -v cloudflared || echo "$HOME/.local/bin/cloudflared")"

if [ ! -x "$CLOUDFLARED" ]; then
  echo "cloudflared not found. Run sh/install-cloudflared.sh first." >&2
  exit 1
fi
if [ ! -f "$HOME/.cloudflared/cert.pem" ]; then
  echo "Not logged in. Run: $CLOUDFLARED tunnel login" >&2
  exit 1
fi

if "$CLOUDFLARED" tunnel info "$TUNNEL" >/dev/null 2>&1; then
  echo "Tunnel $TUNNEL already exists."
else
  "$CLOUDFLARED" tunnel create "$TUNNEL"
fi

# --overwrite-dns: replace an existing record for this hostname, so re-runs don't fail.
"$CLOUDFLARED" tunnel route dns --overwrite-dns "$TUNNEL" "$HOSTNAME"
echo "Done: https://$HOSTNAME -> tunnel $TUNNEL. Start it with sh/tunnel-service.sh start"
