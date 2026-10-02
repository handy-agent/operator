# Operator — session status

## 2026-09-30 — Thumbtack connection (webhook proven, API next)

Goal set by Roman: prove the Thumbtack connection first (webhook + API calls); deploy only after that.
Deploy config will live in a separate deploy repo; production and testing code stay here.

### Done
- A real Direct Lead on production Thumbtack for testing.
- Self-serve Thumbtack webhook → `/webhooks/thumbtack`, events: **messages only**, auth: **none**.
- **Webhook proven end to end**: 4 real `MessageCreatedV4` deliveries received and handled.
- Parser fixed to the real envelope (`event` + `data`): `message_from_event()` in `app/webhooks.py`.
- Thumbtack traffic log built: every webhook + our response and every API call + Thumbtack's response,
  one record per exchange (kind `thumbtack_traffic`, DynamoDB since 2026-10-02). Recorded real traffic
  = future test data (a new connection costs money). Code: `app/db/traffic_log.py`.
- Facts recorded in `REQUIREMENTS.md`: "Environments and credentials", "Thumbtack traffic log",
  "Real webhook deliveries (2026-09-30)".

### State of the test lead
Roman replied by hand in the Thumbtack app → `from: "Business"` → Operator marked the lead taken over
(agent stays quiet on it — by design). Agent replies need a fresh lead and API keys.

### Next
1. ~~Domain~~ — DONE 2026-09-30: **handyagent.dev**. Homepage: `site/index.html`.
2. ~~Named Cloudflare tunnel~~ — DONE 2026-09-30: `https://local.handyagent.dev` (tunnel `handyagent-local`,
   `sh/local-tunnel.sh`, run by `sh/tunnel-service.sh`). Thumbtack webhook switched to it (Roman, 2026-10-01).
3. Thumbtack Partner API access requested 2026-10-01, waiting for review.
   Redirect URIs = `https://local.handyagent.dev/oauth/thumbtack/callback` and `https://api.handyagent.dev/oauth/thumbtack/callback`;
   environments: Production + Staging.
4. Leads events: Roman set up the webhook 2026-10-01 (confirm leads included). Add **leads** to the webhook, so we record a `NegotiationCreatedV4` payload.
5. When keys arrive: Roman puts `THUMBTACK_CLIENT_ID` / `THUMBTACK_CLIENT_SECRET` in `.env` himself;
   build the OAuth Authorization Code flow (callback route + token storage/refresh); set
   `THUMBTACK_API_BASE_URL=https://api.thumbtack.com`; test GET + POST messages on a fresh lead.
6. Before production: add auth to the webhook (anyone with the URL can send fake events now).

### Open / unknown
- Whether Thumbtack sends a message event for every new lead, or only the lead event.
- Whether Thumbtack reviews the website content in the access request.
- Whether Thumbtack accepts `localhost` redirect URIs.
- Agent turn on the replayed first message: timeline stops at `event_received`; the error only shows in
  the Operator terminal window — not checked (expected: missing `THUMBTACK_API_BASE_URL`).
