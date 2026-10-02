#!/usr/bin/env bash
# What: Runs sh/local-tunnel.sh (named tunnel, stable https://local.handyagent.dev) as a background
#       systemd user service (operator-tunnel), so the tunnel survives closing the terminal.
# When: Run from operator/ once after boot (start), then `url` whenever you need the current URL.
# Called by: developer / Claude, by hand. Usage: sh/tunnel-service.sh start|stop|restart|status|url [port]
set -euo pipefail

SERVICE=operator-tunnel
UNIT_FILE="$HOME/.config/systemd/user/$SERVICE.service"
TUNNEL_SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/local-tunnel.sh"
URL=https://local.handyagent.dev
PORT="${2:-8000}"

write_unit() {
  mkdir -p "$(dirname "$UNIT_FILE")"
  cat > "$UNIT_FILE" <<EOF
[Unit]
Description=Cloudflare named tunnel local.handyagent.dev to local Operator (port $PORT)
After=network-online.target

[Service]
ExecStart=$TUNNEL_SCRIPT $PORT
Restart=on-failure
RestartSec=5
EOF
  systemctl --user daemon-reload
}

print_url() {
  echo "Tunnel URL:  $URL"
  echo "Webhook URL: $URL/webhooks/thumbtack"
}

case "${1:-}" in
  start)
    write_unit
    systemctl --user start "$SERVICE"
    print_url
    ;;
  stop)
    systemctl --user stop "$SERVICE"
    ;;
  restart)
    write_unit
    systemctl --user restart "$SERVICE"
    print_url
    ;;
  status)
    systemctl --user status "$SERVICE" --no-pager
    ;;
  url)
    print_url
    ;;
  *)
    echo "Usage: $0 start|stop|restart|status|url [port]" >&2
    exit 1
    ;;
esac
