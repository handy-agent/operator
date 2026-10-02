#!/usr/bin/env bash
# What it does: One-time move of Operator out of runlife into its own repos. Clones
#   handy-agent/operator and handy-agent/operator-deploy into ~/handy-agent, moves everything from
#   this operator/ dir into ~/handy-agent/operator (the .venv is recreated, not moved — venvs hold
#   absolute paths), removes the old dir, and repoints the operator-tunnel systemd user service.
# When it runs: once, by hand (decided 2026-10-01). Refuses to run if the target repo already has code.
# What calls it: nothing — run directly: sh/move-to-handy-agent.sh
set -euo pipefail

SRC="$(cd "$(dirname "$0")/.." && pwd)"
DEST_ROOT="$HOME/handy-agent"
DEST="$DEST_ROOT/operator"
UNIT="$HOME/.config/systemd/user/operator-tunnel.service"

mkdir -p "$DEST_ROOT"
cd "$DEST_ROOT"
[ -d operator ] || git clone git@github.com:handy-agent/operator.git
[ -d operator-deploy ] || git clone git@github.com:handy-agent/operator-deploy.git

# The repo starts with GitHub's README + Python .gitignore only; anything else means already moved.
if [ -n "$(ls -A "$DEST" | grep -v -x -e .git -e README.md -e .gitignore || true)" ]; then
  echo "Refusing: $DEST already has files besides .git, README.md, .gitignore" >&2
  exit 1
fi

# Move (copy, then delete source once the copy succeeded). .venv is skipped and rebuilt below.
# Our README.md replaces GitHub's one-line starter README.
rsync -a --exclude '.venv' "$SRC"/ "$DEST"/

# GitHub's Python .gitignore already covers .env, .venv, __pycache__; add customer data
# (same rule runlife had for operator/data).
if ! grep -qx 'data/\*' "$DEST/.gitignore"; then
  printf '\n# Customer PII and records — never commit. Only the README is tracked.\ndata/*\n!data/README.md\n' \
    >> "$DEST/.gitignore"
fi

python3 -m venv "$DEST/.venv"
"$DEST/.venv/bin/pip" install -q -r "$DEST/requirements.txt"

rm -rf "$SRC"

# Tunnel service pointed at the old path.
if [ -f "$UNIT" ]; then
  sed -i "s#$SRC/sh/local-tunnel.sh#$DEST/sh/local-tunnel.sh#" "$UNIT"
  systemctl --user daemon-reload
  systemctl --user restart operator-tunnel.service
fi

echo "Moved to $DEST"
