#!/usr/bin/env bash
# What it does: One-time move (decided 2026-10-02): all DynamoDB seed files in one place, db/seed/.
#   db/catalog/{services,multipliers}.json + README.md -> db/seed/
#   Deletes the unused competitor-comps pricing (app/pricing.py, db/pricing/) — replaced by the catalog,
#   nothing imported it (the owner's yes, 2026-10-02).
# When it runs: once, by hand.
# What calls it: nothing — run directly: sh/move-seed-folder.sh
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"

if [ -e db/seed ]; then
  echo "Refusing: $REPO/db/seed already exists" >&2
  exit 1
fi

mkdir db/seed
mv db/catalog/services.json db/catalog/multipliers.json db/catalog/README.md db/seed/
rmdir db/catalog
rm app/pricing.py
rm -r db/pricing

echo "Seed files in $REPO/db/seed; unused pricing deleted"
