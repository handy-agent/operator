# Operator — Claude Code (development)

AI agent backend for Handy Agent (handyagent.dev): talks to leads on Thumbtack, notifies the
customer (the handyman), helps estimate the job. Roman is the lead
developer and the first customer.

This file is for developing with Claude Code only. The running agent (Claude Agent SDK) never loads
it: `app/agent.py` passes `setting_sources=[]`, and the agent's own instructions live in `agent/`
(see Layout), read by `app/prompts.py`.

Project working rules: @dev/operator.md

## Layout
- `CLAUDE.md` + `dev/` — Claude Code development only: `operator.md` (working rules),
  `REQUIREMENTS.md` (decisions), `STATUS.md` (current state, next steps), `thumbtack.md`.
- `agent/` — every prompt text, the only place for it: main agent (`main-agent.md` + `reply-style.md` +
  `disclosure-whitelist.md`), sub-agents (`estimator.md`, `item-lookup.md`), `tools.md`, `tool-results.md`,
  `turn-notices.md`. Loaded by `app/prompts.py`; no prompt text in Python. Business profile comes from env
  (`{{BUSINESS_...}}`, `app/business.py`).
- `db/seed/` — all DynamoDB seed files (pricing catalog). All runtime data lives in DynamoDB.
- `app/` — FastAPI app + agent code; `tests/` — unittest (`.venv/bin/python -m unittest discover tests`).
- `sh/` — scripts (see `sh/README.md`). `site/` — handyagent.dev homepage.
- Deploy: separate repo `../operator-deploy` (github.com/handy-agent/operator-deploy).

## Rules
- Shell work goes in documented `sh/` scripts — no one-off commands. Header on every script: what it
  does, when it runs, what calls it. Never delete or overwrite a script without Roman's yes.
- Always write tests. Follow existing code conventions. Prefer explicit over clever code.
- Feature branch for new work. Conventional commits (`feat:`, `fix:`, `docs:`, `refactor:`), short.
  No commit until Roman reviews it.
- Never commit secrets (`.env`). Customer data (names, phones, addresses) stays out of git.
- Never send a lead a price, a date/time, or any commitment without Roman's explicit yes.
- Never pay for leads/credits, change Thumbtack settings, or enter passwords/payment details.
- State assumptions explicitly; say "I don't know" when unsure. Don't duplicate logic or text —
  reference it.
- Execute short, unambiguous, reversible orders right away.
- Be direct and concise; no rationale unless asked.
