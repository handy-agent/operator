#!/usr/bin/env bash
# What it does: One-time move (decided 2026-10-02) of everything simulator into one top-level folder:
#   app/sim/          -> sim/         (simulator code; outside app/, so it's never deployed)
#   db/records/sim/*  -> sim/runs/    (the sim windows' conversation files; git-ignored)
#   Rewrites imports: sim code's relative app imports (from ..x) -> absolute (from app.x);
#   app.sim -> sim in tests and sh/ scripts; app/sim/ -> sim/ in comments and docs.
#   db/ is left holding only data that moves to DynamoDB.
# When it runs: once, by hand.
# What calls it: nothing — run directly: sh/move-sim-folder.sh
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"

if [ -e sim ]; then
  echo "Refusing: $REPO/sim already exists" >&2
  exit 1
fi

mv app/sim sim
rm -rf sim/__pycache__
mkdir -p sim/runs
if [ -d db/records/sim ]; then
  find db/records/sim -mindepth 1 -maxdepth 1 -exec mv {} sim/runs/ \;
  rmdir db/records/sim
fi

# Sim code: relative imports of app modules -> absolute.
sed -i -e 's/^from \.\. import /from app import /' -e 's/^from \.\.\([a-z_]\)/from app.\1/' sim/*.py

# Module path app.sim -> sim (tests, scripts).
sed -i 's/\bapp\.sim\b/sim/g' tests/*.py tests/live/*.py sh/sim.sh sh/chat.sh

# Comments and docs: app/sim/ -> sim/, old run-file location -> sim/runs/.
sed -i 's#app/sim/#sim/#g' app/*.py app/*/*.py sim/*.py dev/REQUIREMENTS.md
sed -i 's#db/records/sim/<id>/#sim/runs/<id>/#' sh/sim.sh

# Git-ignore the run files.
printf '\n# Simulator conversation files.\nsim/runs/\n' >> .gitignore

echo "Moved simulator to $REPO/sim (runs in sim/runs/)"
