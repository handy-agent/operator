#!/usr/bin/env bash
# What it does: One-time split of Claude files: moves the files the Agent SDK agent reads at runtime
#   (reply-style.md, disclosure-whitelist.md) into agent/, so the repo root only holds files for
#   developing with Claude Code (CLAUDE.md, operator.md).
# When it runs: once, by hand (decided 2026-10-01).
# What calls it: nothing — run directly: sh/split-claude-files.sh
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$REPO/agent"
for f in reply-style.md disclosure-whitelist.md; do
  if [ -e "$REPO/agent/$f" ]; then
    echo "Refusing: $REPO/agent/$f already exists" >&2
    exit 1
  fi
  mv "$REPO/$f" "$REPO/agent/$f"
done
echo "Moved agent prompt files into $REPO/agent/"
