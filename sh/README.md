# Operator scripts

Every script starts with a header comment: what it does, when it runs, what calls it.
Run from the `operator/` dir.

- `install-cloudflared.sh` — one-time install of cloudflared to `~/.local/bin`.
- `local-tunnel-setup.sh` — one-time: creates named tunnel `handyagent-local`, DNS `local.handyagent.dev`
  (needs `cloudflared tunnel login` first).
- `local-tunnel.sh [port]` — named tunnel, stable `https://local.handyagent.dev` -> local Operator.
- `tunnel.sh [port]` — (fallback) quick tunnel with a random URL; public HTTPS tunnel to local Operator (default port 8000) for testing webhooks.
  Start it before or after Operator — order doesn't matter; restarting Operator keeps the URL.
- `start.sh [port]` — starts the tunnel if needed and opens a new terminal window running Operator.
- `import-thumbtack-prices.sh ["Home Improvement"]` — fills db/seed/services.json from Thumbtack cost guides
  (then `dynamo-seed.sh` to load it).
- `live-estimate-scenarios.sh` — live agent checks: approve, changed price, photos first, lead haggles.
- `sim.sh [--telegram <account_id>]` — two-window simulator: Chat (lead messages; `/out` = you by hand) + Notes (notes, instructions to the agent, `/resume`). Nothing sent to Thumbtack. `--telegram <account_id>`: Telegram instead of the Notes window; the sim lead belongs to that account.
- `account-settings.sh <account_id> [key=value ...]` — show/change a customer's settings (reply timing,
  first reply right away, hold time, alarm, session warmth) while Operator runs.
- `connect-telegram.sh <account_id> ["Business name"]` — emulates connecting a customer: creates the account, prints a one-time Telegram link.
- `chat.sh` — local chat simulator: you type as the customer, Operator replies. Nothing sent to Thumbtack.
- `run.sh [port]` — starts DynamoDB Local if needed, then Operator locally (uvicorn, port 8000, auto-reload).
- `dynamo-local.sh start|stop|reset|status` — DynamoDB Local in Docker at `http://localhost:8001`, data on
  volume `operator-dynamodb-data`; `start` also creates the table. `reset` deletes all local data.
  Started automatically by `run.sh`, `sim.sh`, `chat.sh`. Needs your user in the `docker` group.
- `dynamo-seed.sh` — loads `db/seed/` (pricing catalog) into DynamoDB — local, or a stage's table from env.
  Runs by itself on a fresh local table. Safe to rerun.
- `tunnel-service.sh start|stop|restart|status|url` — runs `local-tunnel.sh` in the background (systemd user
  service) until stopped or reboot. `url` prints the webhook URL.

## Telegram
One product bot for all customers. Each customer connects with a one-time link; notes about their leads
come to their private chat with the bot, one topic per lead, title = who's talking (🤖 agent / 👤 them).
Typing in a lead's topic = instruction to the agent; `/pause`, `/resume` or the buttons.

Bot setup (once, by us):
1. @BotFather: `/newbot`. Token -> `.env` `TELEGRAM_BOT_TOKEN`.
2. @BotFather: turn on topics (threaded mode) for the bot — needed for one topic per lead.
   `connect-telegram.sh` warns if it's off.

Connect a customer (emulated):
1. `sh/sim.sh --telegram <account_id>` (or Operator running) so the bot answers.
2. `sh/connect-telegram.sh <account_id> "Business name"` -> open the link on the phone, tap Start.
3. Type a lead message in the Chat window; the note arrives on the phone.

Only one of Operator / a Telegram sim run can poll Telegram at a time. Production sets
`TELEGRAM_WEBHOOK_URL` + `TELEGRAM_WEBHOOK_SECRET` instead of polling.
