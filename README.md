# Operator

AI assistant that watches lead platforms and handles first-contact replies on the business owner's behalf.
Built platform-agnostic so it can extend beyond Thumbtack later (e.g. Yelp) without a rewrite.

## Design
- **Core** (this folder): platform-agnostic logic — reply rules (`agent/reply-style.md`), lead records (DynamoDB), hand-off/notify rules.
- **Platform adapters**: one per lead source, each owning that platform's detection + send mechanics.
  - Thumbtack — first adapter, live now (`app/messaging/thumbtack.py`, notes in `dev/thumbtack.md`).
  - Future: Yelp, etc. — same contract, new adapter, core stays unchanged.

## Stack
Python + FastAPI + Claude Agent SDK + DynamoDB. Layout: `app/` (runtime), `agent/` (agent prompts),
`sim/` (simulator), `db/seed/` (DynamoDB seed data), `tests/`, `sh/` (scripts), `dev/` (dev notes).
`.env.example` -> `.env`. Local DynamoDB runs in Docker (`sh/dynamo-local.sh`).

Run locally:
```
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
sh/start.sh          # tunnel + DynamoDB Local + app on :8000
sh/sim.sh            # or: simulator, nothing sent to Thumbtack
```
Tests: `.venv/bin/python -m unittest discover tests`. Scripts: `sh/README.md`.

AWS deployment lives in the separate repo github.com/handy-agent/operator-deploy.

## Status
See `dev/STATUS.md` (current state, next steps) and `dev/REQUIREMENTS.md` (decisions).
