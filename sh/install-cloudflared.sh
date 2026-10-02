#!/usr/bin/env bash
# What: Installs the cloudflared binary to ~/.local/bin (no sudo). Skips if already installed.
# When: Once per machine, before the first run of tunnel.sh.
# Called by: developer / Claude, by hand. tunnel.sh tells you to run it if cloudflared is missing.
set -euo pipefail

if command -v cloudflared >/dev/null; then
  echo "cloudflared already installed: $(cloudflared --version)"
  exit 0
fi

case "$(uname -m)" in
  x86_64)  ARCH=amd64 ;;
  aarch64) ARCH=arm64 ;;
  *) echo "Unsupported arch: $(uname -m)" >&2; exit 1 ;;
esac

BIN_DIR="$HOME/.local/bin"
mkdir -p "$BIN_DIR"
curl -fsSL -o "$BIN_DIR/cloudflared" \
  "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-$ARCH"
chmod +x "$BIN_DIR/cloudflared"

"$BIN_DIR/cloudflared" --version
case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) echo "Add $BIN_DIR to PATH to use cloudflared directly." ;;
esac
