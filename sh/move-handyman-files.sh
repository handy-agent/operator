#!/usr/bin/env bash
# What it does: One-time move of the files Operator still read from runlife's handyman/ folder
#   (reply-style.md, pricing/) into this repo, so the repo runs on its own.
# When it runs: once, by hand (decided 2026-10-01), after sh/move-to-handy-agent.sh.
# What calls it: nothing — run directly: sh/move-handyman-files.sh
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
HANDYMAN="$HOME/runlife/claude-config/handyman"

for f in reply-style.md pricing; do
  if [ -e "$REPO/$f" ]; then
    echo "Refusing: $REPO/$f already exists" >&2
    exit 1
  fi
done

mv "$HANDYMAN/reply-style.md" "$REPO/reply-style.md"
mv "$HANDYMAN/pricing" "$REPO/pricing"
echo "Moved reply-style.md and pricing/ into $REPO"
