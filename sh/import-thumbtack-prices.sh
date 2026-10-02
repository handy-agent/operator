#!/usr/bin/env bash
# What: Imports Thumbtack's public cost guides into db/seed/services.json (then sh/dynamo-seed.sh) (market ranges + baseline
#       flat prices). Default top category "Home Improvement" (~300 pages, ~5 min at 1 request/sec).
#       Hand-curated subservices keep their pricing; only their market range is refreshed.
# When: By hand, when market prices should be refreshed.
# Called by: developer / Claude, by hand. Usage: sh/import-thumbtack-prices.sh ["Home Improvement"]
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
exec .venv/bin/python -m app.importers.thumbtack_prices "$@"
