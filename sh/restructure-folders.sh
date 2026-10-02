#!/usr/bin/env bash
# What it does: One-time folder restructure (decided 2026-10-01) into three clear places:
#   dev/   — files for developing with Claude Code (operator.md, REQUIREMENTS.md, STATUS.md, thumbtack.md);
#            CLAUDE.md stays at the root, where Claude Code loads it.
#   db/    — all data: records/ (was data/, git-ignored), catalog/, pricing/.
#   agent/ — the Agent SDK agent's prompt files (already there).
# When it runs: once, by hand.
# What calls it: nothing — run directly: sh/restructure-folders.sh
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"

for p in dev db; do
  if [ -e "$p" ]; then
    echo "Refusing: $REPO/$p already exists" >&2
    exit 1
  fi
done

mkdir dev db
mv operator.md REQUIREMENTS.md STATUS.md thumbtack.md dev/
mv data db/records
mv catalog pricing db/
echo "Restructured: dev/, db/ (records, catalog, pricing), agent/"
