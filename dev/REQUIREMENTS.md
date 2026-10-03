# Operator — Requirements

Working notes, decided piece by piece. Not a build plan — nothing here gets implemented until
Roman confirms the whole thing.

## Terms (Roman, 2026-09-25)
- **Customer** — a handyman using Operator (an account; Roman is the first).
- **Lead** (or client) — a person asking for a job on Thumbtack (or another platform).
  Thumbtack's own API says "customer" for the lead; that stays only in its field names.

## What it is
AI assistant/operator that communicates with leads on Roman's behalf. Own project (will move
out of the `runlife` repo into its own GitHub repo later — everything stays self-contained
under `operator/` for that reason).

## Platform scope
- Thumbtack first. Built platform-agnostic so it can extend to other lead sources (e.g. Yelp)
  later without a rewrite — one adapter per platform.

## Flow (as described so far)
1. Lead sends a message on Thumbtack.
2. We provide Thumbtack a webhook link; the message arrives there (receive-only, see below).
3. Operator reads the message and drafts an auto-response.
   - Must be polite and **not** sound AI-generated — human, plain, like a busy local pro texting.
   - Clarifies all job details needed to quote (see `agent/reply-style.md` for the existing rules:
     no pricing, no date/time confirmation, no commitments — those stay with Roman).
4. Operator sends the reply back via **Thumbtack's Partner Messages API** (Roman's decision,
   2026-09-22) — not Chrome automation. Uses the Partner Platform (developers.thumbtack.com);
   access assumed granted, not treated as an open blocker.
5. Notify Roman: on his phone, two-way — see "Phone channel" below.

## Main workflow (Roman, 2026-09-22)
1. Webhook notification arrives (new lead / new message).
2. Operator fetches the full lead (negotiation) from the Thumbtack API.
3. Lead, conversation history, estimate, and contact info get stored in a database.
   - Start simple — even plain markdown files are fine for a first version. Doesn't need to be
     a real DB on day one.
4. Operator clarifies all details with the customer (per `agent/reply-style.md`) until it has
   everything needed to produce an estimate.
5. Estimate step:
   - First look for a match in the existing pricing data — originally `pricing/` CSVs, now the catalog (e.g.
     `furniture-assembly.csv`: competitor hourly rates scraped from TaskRabbit/Thumbtack by
     service + area, already collected 2026-09-21). This is the "db for estimates" — same
     approach to be reused/extended for other services.
   - If no match exists for the service, the operator does online research (same comps-gathering
     method already used for furniture-assembly) to produce pricing data, and that gets added to
     the pricing DB for future reuse.
   - Estimate is sent as a plain text message via the Messages API (Roman's decision, 2026-09-22)
     — not Thumbtack's native quote/invoice feature. Same `POST .../messages` endpoint as any
     other reply. Still needs Roman's yes before it goes out (price stays his call per
     `agent/reply-style.md`); the operator prepares it, doesn't send it unapproved.

## Agent loop design (2026-09-23) — BUILT
Discussed and agreed direction for wiring the Claude Agent SDK into a real loop. Now built and
tested (see "What's built" below) except where noted as still open.
- **Hybrid session model (revised 2026-09-23, replaces pure stateless):**
  - While a lead is actively responding (fast back-and-forth), keep the session warm — new
    webhook events for that negotiation join the same live SDK session instead of each rebuilding
    context from scratch.
  - After a period of inactivity (timeout — exact duration not decided yet), the session is
    considered closed.
  - The next event on that lead — another webhook, or Roman taking a call/manually re-engaging —
    rebuilds the session fresh rather than resuming the old one.
  - On rebuild, if there's prior history, first make an API call to refresh the negotiation's
    status and messages ("just in case" something happened while no live session was held — a
    missed webhook, Roman replying manually, a status change) before resuming the conversation.
  - **Every inbound and outbound message gets saved to our own DB regardless of session
    lifecycle** — the persisted record is independent of whether the live SDK session is warm or
    was just rebuilt.
  - Built using `ClaudeAgentOptions.resume` (confirmed from the installed SDK's source: "Session
    ID to resume. Loads the conversation history from the specified session"). Warm/cold decided
    by `Session.last_activity_at` vs. `WARM_TIMEOUT_SECONDS` (`app/db/sessions.py`) — currently a
    30-minute placeholder default, Roman hasn't picked a real value yet.
- **Estimate drafting is decoupled from sending.** A `propose_estimate` tool writes an `Estimate`
  record (`status="draft"`) and stops — it never sends a price itself. Sending only happens once
  `status` flips to `approved` (approval mechanism still TBD).
- **Tools for the live conversation loop:** `send_message`, `get_messages` (built), plus new:
  `propose_estimate` (price estimator, drafts only), `record_lead_detail` (updates the Lead
  record as details get clarified), a **calendar tool** and a **distance/travel tool** (both
  new, see below).
- **Pricing-research is an async tool, not part of the live flow.** Adding new pricing data to
  the local DB (web research for a service with no match yet) runs separately/in the background —
  it does not block or happen inline during a customer conversation turn.
- **Idempotency:** built — `app/db/idempotency.py`, keyed on `messageID` (falls back to a
  negotiationID+sentAt composite if that field is absent — real webhook field name unconfirmed).

### Stop conditions — operator must NOT auto-send, must wait for Roman
1. **Estimate drafted** → waits for Roman's approval → once approved, operator texts it. (Same
   rule as before, now formalized as a tool + DB status flow.)
2. **Scheduling proposal drafted** → same approval gate as the estimate. Confirming a date/time
   with the customer also needs Roman's explicit yes before it's sent — not just price.
3. **Negotiation status has moved to "scheduled" or further along** → stop auto-replying
   entirely, nothing left to negotiate. Maps directly to the job-status values already found in
   the Thumbtack API (`appt_scheduled`, `job_complete`, `invoice_paid`, `customer_cancel`,
   `pro_cancel` — anything past `not_scheduled`).

### New tools
- **Calendar tool:** integrates Roman's calendar (Google Calendar, per his stack) so the agent
  can check/propose availability when negotiating scheduling. Scheduling proposals still go
  through the approval gate above before being sent to the customer.
- **Distance/travel tool:** calculates distance from Roman's base (or another job) to the
  customer's location. Feeds into both the estimate (gas/travel time cost) and scheduling
  (travel time between jobs affects which slots are actually available).

## Stack
- Python + FastAPI + Claude Agent SDK (`claude-agent-sdk` pip package, Python 3.10+). Auth: see
  "Claude auth: Claude Platform on AWS" below.
- Split (Roman, 2026-09-30): deploy config lives in a separate deploy repo; production and testing
  code live here.
- AWS deployment (Roman, 2026-10-01) — BUILT 2026-10-03 in `../operator-deploy` (how it works: its
  `README.md`; decisions, status, open points: its `PLAN.md`). develop infra is up, not deployed yet.
  - Same shape as github.com/realestate-lab/downpayment_deploy: separate deploy repo, a local Docker
    sandbox, per-stage scripts (`stages/<stage>/init.sh|deploy.sh|…`).
  - Compute: one EC2 server (t4g.small, 2 GB, ~$17/mo) running Operator as one process — not Lambda.
    Why: Lambda needs the in-memory per-lead timers/batching, warm sessions and polling rebuilt
    (queues, locks); a server keeps them. EC2 over Lightsail: IAM role for Claude Platform on AWS
    (no static key); only ~$5/mo more.
  - DB: DynamoDB, replacing the files under `data/`. Local: DynamoDB Local in Docker (as in the example).
    BUILT 2026-10-02: see "DynamoDB (built)" below.
    Local data persists on a Docker volume (Roman, 2026-10-01) — not `-inMemory` like the example;
    survives restarts.
  - Local environment runs the whole thing locally before deploy.
  - `data/` and `pricing/` get replaced by DynamoDB (Roman, 2026-10-01). Needs documented `sh/` scripts
    to init (seed) DynamoDB with that data — local and per stage.
  - Repos (Roman, 2026-10-01): code in github.com/handy-agent/operator, deploy in
    github.com/handy-agent/operator-deploy, both cloned under `~/handy-agent/`. Moved out of runlife;
    the repo is self-contained — everything the agent reads lives inside it.
  - Deploy ships only runtime: `app/`, `agent/`, `requirements.txt` (+ `db/` as DynamoDB seed data).
    Never `CLAUDE.md`, `dev/`, `tests/`, `.env` (Roman, 2026-10-01).
  - Stages (Roman, 2026-10-02): `develop` / `demo` / `production`, same as real estate.
  - Infra (2026-10-02): SST v3, like real estate, but `sst.config.ts` lives in operator-deploy (not
    here). Deploys run by hand via `stages/<stage>/deploy.sh` there (real estate has no CI either).
  - Ingress (Roman, 2026-10-02): API Gateway HTTP API + VPC Link (Cloud Map) → uvicorn on the EC2
    server. Rule: routing must cost no more than real estate's (~$1 per million requests). Rejected:
    CloudFront VPC origin (server must sit in a private subnet → NAT ~$7+/mo), ALB (~$18/mo), Caddy
    (cert renewal on the box). Cloudflare Tunnel is OK as a fallback.
    - API Gateway cuts requests at 30 s: webhook routes must return fast. Checked 2026-10-02: Thumbtack
      route hands off to the scheduler, Telegram route to `handle_soon` — both OK.
  - Stages × Thumbtack (Roman, 2026-10-02):

    | Stage | Thumbtack env | Thumbtack keys | Pro account | Customer test account | Domain | Webhook URL | OAuth redirect |
    |---|---|---|---|---|---|---|---|
    | local | production (now), staging later | production (now), staging later | ATX Handy Pros | friend's real account | `local.handyagent.dev` (Cloudflare Tunnel) | `https://local.handyagent.dev/webhooks/thumbtack` | `https://local.handyagent.dev/oauth/thumbtack/callback` (registered) |
    | develop | staging | staging | staging test pro (unknown) | staging test customer (unknown) | `dev-api.handyagent.dev` | `https://dev-api.handyagent.dev/webhooks/thumbtack` | `https://dev-api.handyagent.dev/oauth/thumbtack/callback` (to request) |
    | demo | staging | staging | staging test pro, shared or its own (unknown) | staging test customer (unknown) | `demo-api.handyagent.dev` | `https://demo-api.handyagent.dev/webhooks/thumbtack` | `https://demo-api.handyagent.dev/oauth/thumbtack/callback` (to request) |
    | production | production | production | ATX Handy Pros, later each paying handyman | real customers | `api.handyagent.dev` | `https://api.handyagent.dev/webhooks/thumbtack` | `https://api.handyagent.dev/oauth/thumbtack/callback` (to request) |

    - Until the new redirects are approved, every stage logs in through `local.handyagent.dev`.
    - Only one stage at a time is registered on your real Thumbtack account; right now that's local.
    - Each stage has its own Telegram bot, webhook secret and IAM role.
    - `dev-api`, `demo-api`, `api` records are created in Cloudflare by each stage's first `init.sh`
      (operator-deploy). `dev-api` exists since 2026-10-03; the hand-made placeholders were deleted.

## Layout
- Standard standalone Python FastAPI layout (done): `app/` (runtime), `agent/`, `sim/` (simulator, never
  deployed), `db/seed/` (DynamoDB seed files), `tests/`, `sh/`, `dev/`.

## Confirmed from Thumbtack docs (2026-09-22)
- **Receiving:** self-serve webhook (Apps → Manage webhooks in the Thumbtack dashboard), no
  approval needed. Per-business-profile. Can choose to receive leads (name + phone, no email),
  messages, reviews. Testable, has a delivery log with error codes.
- **Webhooks are one-way / read-only** — Thumbtack → us only. Can't send replies through it.
- **Sending:** requires the Partner Platform's Messages API (developers.thumbtack.com), which is
  gated behind "Request Access" — approval not yet obtained, eligibility/timeline unknown.

## Environments and credentials (Thumbtack docs, 2026-09-30)
Source: developers.thumbtack.com/docs/getting-started/environments and .../authentication.
- Keys are not self-serve: Thumbtack issues them via Request Access (developers.thumbtack.com/request-access).
  Two sets of clientID + clientSecret — production and staging; each works only in its own environment.
- Production: API `https://api.thumbtack.com/api/`, auth `https://auth.thumbtack.com/oauth2/auth`,
  token `https://auth.thumbtack.com/oauth2/token`, web thumbtack.com.
- Staging: API `https://staging-api.thumbtack.com/api/`, auth `https://staging-auth.thumbtack.com/oauth2/auth`,
  token `https://staging-auth.thumbtack.com/oauth2/token`, web staging-partner.thumbtack.com.
- OAuth2: Authorization Code (acts for the pro business; `audience=urn:partner-api`, `state` >= 8 chars)
  or Client Credentials. Access token 1h; refresh token 180 days, single-use, needs `offline_access`.
  Scopes per route in the API Reference (`supply::` prefix for pro-side partners).
- Self-serve webhooks (thumbtack.com/pro/webhooks/list) need no API keys.
- Company name: **Handy Agent** (Roman, 2026-10-01).
- Product domain: **handyagent.dev** (Roman, 2026-09-30, Cloudflare Registrar). Planned hosts:
  `local.handyagent.dev` (named tunnel to local), `api.handyagent.dev` (production).

## Thumbtack traffic log (Roman, 2026-09-30) — BUILT
Log every Thumbtack exchange, requests and responses, both directions, for future testing — a new
Thumbtack connection costs money, so recorded real traffic is the test data.
- Where: DynamoDB, kind `thumbtack_traffic` (was files under `data/thumbtack_traffic/`). One record
  file per exchange: webhook delivery + our response (inbound), API call + Thumbtack's response (outbound).
  Authorization headers redacted. Code: `app/db/traffic_log.py`.

## Real webhook deliveries (2026-09-30)
Self-serve webhook, no auth chosen, events: messages (leads not yet enabled — Roman to add).
- Envelope: `{"event": {eventType, description, webhookID, triggeredAt}, "data": {...}}`.
- `MessageCreatedV4` data: messageID, negotiationID, customer{customerID, displayName},
  business{businessID, displayName}, from, text, sentAt.
- `from` values seen: `"Customer"` (lead), `"Business"` (Roman replying by hand in the Thumbtack app).
- Pro-side text can contain `\r\n` line breaks.
- No signature/auth header on deliveries (with "no auth" selected). Sender IP seen: 54.85.118.204.
- `NegotiationCreatedV4` (new lead) payload not seen yet.

## More from Thumbtack Partner Platform docs (2026-09-22)
- Leads are called **negotiations** in the API (`/api/v4/negotiations/{negotiationID}`). A
  webhook (`NegotiationCreatedV4`) fires on new leads; full details fetchable via `GET`.
- Messages: `GET /api/v4/negotiations/{id}/messages` (history) and
  `POST /api/v4/negotiations/{id}/messages` with `{"text": "..."}` (send) — plain text only, no
  structured message types seen.
- Each message has a `from` field (seen: `"Customer"`) — presumably distinguishes sender side,
  needed for hand-off detection (see below). Exact enum values not yet confirmed.
- **No Quotes/Estimates API endpoint found** in the Pro Integrations nav (only Leads/negotiations,
  Messages, Reviews, Pro Profiles, Business Phone Numbers, Post job signals, Webhooks). The
  negotiation object description mentions "Invoices and scheduling — included once a pro has
  sent a quote or scheduled the job," implying quote/invoice data shows up as part of the
  negotiation once sent, but there's no API to *send* a quote through that way. Decision
  2026-09-22: skip Thumbtack's native quote flow entirely — the estimate is just sent as a plain
  text message via the Messages API, same as any other reply.
- `POST /api/v4/negotiations/{id}/job-status` reports job lifecycle to Thumbtack (not_scheduled,
  appt_scheduled, job_complete, invoice_paid, customer_cancel, pro_cancel) — separate from
  quoting; this is us telling Thumbtack the job's status, not sending a price.

## New requirements from Roman (2026-09-22)
- **Hand-off awareness:** the operator must know when Roman takes over messaging a lead manually
  (e.g. replying himself in the Thumbtack app) and stop auto-replying to that thread. Likely
  approach: track messages the operator itself sent via the API; if a new pro-side message shows
  up on a lead that the operator didn't send, treat it as Roman taking over. Depends on
  confirming the `from` field's values — not yet verified.
- **Estimate-approval awareness:** the operator must know when Roman has approved an estimate for
  a lead. Resolved 2026-09-22: since there's no Quotes/Estimates API, the estimate is just a text
  message sent via the Messages API — same mechanism as any other reply, same approval rule
  (price stays Roman's call, operator drafts, doesn't send unapproved).

## Human control / takeover (Roman, 2026-09-22)
- Roman can interrupt the operator on a given lead with a command ("I'll take it from here").
- **Replying by hand = takeover (Roman, 2026-09-23) — BUILT.** As soon as Roman sends a message to the
  customer himself, the operator stops on that lead. It resumes only on Roman's explicit command
  (`/resume` in the simulator's Roman window). After resuming, prices/times Roman stated count as approved.
- **One person (Roman, 2026-09-24).** The lead talks to one person, Roman. The agent's and Roman's messages
  are one voice: the agent never repeats or restates anything already said in the thread by either of them.
- The lead's session must **stay alive** across an interrupt/takeover — not torn down.
- While Roman has taken over, the operator keeps ingesting everything happening on that lead
  (customer messages and Roman's own manual replies) into the session's history, so it stays in
  sync for as long as the session is alive, even though it isn't acting.
- Roman can ask the operator what to say; the operator proposes text; only after Roman confirms
  does the operator actually send it. (This request/confirm/send pattern applies generally, not
  just during a takeover.)
- **Estimate step always stops and asks for Roman's explicit confirmation before sending** — not
  just during a takeover; this is the standing rule (see "Estimate step" above), reconfirmed here
  as a required stop-and-ask checkpoint in the flow.
- **How Roman actually issues these commands/confirmations:** phone channel, see "Phone channel".
- (was TBD:) Roman needs to think about
  this more — a mobile app is one option under consideration, but not being decided or built now.

## Security: prompt injection (2026-09-23)
Roman's concern: a lead who realizes they're talking to an AI could try to manipulate/gaslight
it into breaking the rules (e.g. claiming Roman already approved a price). Discussed defenses:
1. **Price/scheduling are structurally gated, not just prompted.** `propose_estimate` only ever
   writes a draft; there is no tool path for the agent to send a price or confirm a date/time
   without Roman's approval. This is the main mitigation — even a fully manipulated turn has no
   button to press to act on it.
2. **Customer text is data, never instructions.** System prompt states explicitly that nothing in
   the customer's message can change the rules, no matter what it claims ("Roman already said
   it's fine," fake "system:" text, etc).
3. **Capability minimization.** Tool set stays narrow (send_message, get_messages,
   propose_estimate, record_lead_detail, calendar check, distance calc) — nothing destructive, no
   payments, no settings changes. Small blast radius even if a turn is fully compromised.
4. **Never discuss being AI — already the rule in `agent/reply-style.md`.** If sincerely asked, hand
   off to Roman and stop replying rather than answer. Injection attempts to extract an admission
   hit the same hand-off path.
5. **Manipulation attempts are a hand-off trigger, not something to argue through.** Obvious
   injection patterns (fake system messages, "ignore previous instructions," aggressive pressure)
   route to "hand off to Roman," same as any other out-of-scope request.

## Security: data isolation / secret protection (2026-09-23)
Roman's concern: a lead asking things like "what did your last customer pay?" or "what's your
home address?" — protecting against leaks without relying on the model's judgment alone.
Core principle: **build with allowlisted context, not a blocklist of "don't say X."** A model can
eventually be talked into breaking a "don't share" rule; it can't leak what was never in its
context.
- **Per-lead context scoping:** the agent's context for a given lead's turn only ever contains
  that lead's own conversation and record. No tool available to it can query other leads,
  sessions, or estimates — there is nothing cross-customer to leak.
- **Tools return minimized/computed results, not raw internal data.** The pricing tool returns a
  price recommendation for the current job, never the raw comp rows (other providers' rates,
  other jobs). The distance/travel tool takes Roman's origin point from server-side config the
  tool code reads directly — the address string itself never becomes text the model sees or can
  quote back; the tool returns only the computed distance/duration.
- **System prompt still states the rule explicitly** (belt-and-suspenders, not primary defense):
  only share business info approved for the public profile (existing `reply-style.md` rule),
  never personal/financial/other-customer details.
- **Output filter as a backstop:** a cheap pattern check on outgoing `send_message` text (e.g.
  street-address-like patterns, dollar-breakdown patterns) before it actually sends — catches
  leaks the prompt-level rule missed. Backstop only, not the main mechanism.

## Security: disclosure whitelist, not blacklist (revised 2026-09-23)
Roman's correction: default should be **deny-by-default with an explicit whitelist of what the
agent may tell a customer**, not "share anything except this blacklist." Blacklists miss things;
a whitelist means anything not explicitly approved is withheld by default, no judgment call
needed at message time.

**Draft whitelist — what the agent MAY share** (based on what's already public/approved):
- Business name: "Roman, ATX Handy Pros"
- Services offered: furniture assembly, fitness equipment assembly, barbecue/grill services
  (Roman's starting services, 2026-09-19 — cooking-for-party not yet approved, permits unverified)
- Service area: North Austin preferred, all Austin OK
- Non-committal process language: "happy to help," "could you send photos / preferred day,"
  "I'll get back to you with a price" (per `agent/reply-style.md` base reply shape)
- Requests for job details: what the job is, photos, area/zip, preferred timing (asking only,
  never confirming), access notes

**Everything else defaults to withheld**, including but not limited to: price/cost figures,
dates/times/scheduling confirmations, any other customer's or job's info, Roman's personal
details (home address, phone, personal schedule, finances), internal operations (automation/AI
involvement, tools used, lead costs, how leads are handled), licensing/insurance claims unless
explicitly approved as fact.

**Next step:** this whitelist should become the actual thing the system prompt is built from
(not just prose in this doc) — likely its own file (e.g. `disclosure-whitelist.md`) that
`app/system_prompt.py` reads directly, same pattern as `reply-style.md`. Not
built yet — Roman should review/edit the draft list above first.

## Human-like reply timing (Roman, 2026-09-23) — BUILT (app/reply_timing.py; quiet hours not built)
Reply like a busy pro texting, not a bot answering instantly. Leads often split one thought across
several texts (link in one, day in the next) — a human reads them all and answers once.

Proposed design:
- **Wait before replying.** On a customer message, don't run the agent right away. Wait a random
  20-60s (reading + typing time; was 60-180s, shortened by Roman 2026-09-24).
- **Batch follow-ups.** If another message from the same lead arrives during the wait, restart the
  wait (capped at ~5 min total), then reply once to everything. The agent already reads the whole
  thread via `get_messages`, so it sees all the new texts.
- **One reply, not one per message.** Never answer each text separately.
- Per-lead only: other leads are not delayed by one lead's wait.
- Delays configurable via env, so the simulator can use short ones (e.g. 5-15s). The simulator
  needs non-blocking input so you can send a second text during the wait.

Open questions for Roman:
- Quiet hours: hold replies overnight (e.g. 9pm-7am) like a human would, or reply any time?
- Delay range: is 1-3 min right?

## Price suggestion for Roman (Roman, 2026-09-23) — BUILT (see "Built: simulator, reply timing, pricing, estimates")
When a lead needs a price, the agent's note to Roman includes a suggested price with the reasons, e.g.:
"My suggestion: $250. Lead cost is high ($20), and it's far from you, so gas is a big part.
Normal price for the same job: $100-250 (source)."
Inputs so far: lead cost, travel distance/gas, market range for the same job (looked up somewhere,
with source). Roman approves or changes it; the agent never sends a price on its own.
Checking priority (which source to check first): Roman to describe next.

Pricing data model (Roman, 2026-09-23):
- Many services, each with subservices (furniture assembly is just one). Mirror Thumbtack's category
  structure, but platform-neutral (other platforms later) — map to each platform's categories.
- Subservices have quantity (number of items) and their own multipliers (e.g. with vs without instructions).
- Order-level multipliers, both directions (>1 or <1): e.g. lead cost, distance/gas, availability
  (almost fully booked -> greedy; slow week -> cheaper).
- Storage: JSON now (not md), DynamoDB later — so shape records as DynamoDB items.
- Nice to have: show the most similar past job (ours) as an example next to the suggestion.
- TBD: post the same job on TaskRabbit or similar to collect real offers as a market check.
- Multipliers compound (1.3 x 1.3 = 1.69). Suggested price rounds to the nearest $5.
- Location multiplier: at least per state (lookup table by state; 1.0 by default when not listed).
- Market ranges source: Thumbtack cost guides, e.g. https://www.thumbtack.com/p/handyman-prices
  (national ranges by project type/service, hourly rates, location-specific rates). Populate the
  subservices' `market` field from these, with source URL and date checked.
  Index of all cost guides: https://www.thumbtack.com/prices (~500 pages, 5 top categories).
  Subcategory pages go deeper, e.g. /p/furniture-assembly-cost has national range ($102-221,
  typical $148), hourly ($40-100, avg $65), and a price table by item count (1: $120, 2: $160,
  3: $200 ... 10: $450) — use that table shape for quantity pricing.
- The suggestion is a baseline: the location average for the subservice with all multipliers
  applied. Job size (how big the bed is, etc.) is only knowable from photos/links, so Roman checks
  those himself before confirming the price.
- Pricing shape differs per subservice (items make sense for furniture, not for everything): each
  subservice has a `pricing.model` (e.g. per_item with a qty table, flat, hourly, per_unit like sq ft)
  and only that model's fields.

## Open / unverified
- Multiplier values in `db/seed/multipliers.json` are placeholders; need Roman's real numbers.
- Quiet hours (hold replies overnight): not decided.
- Confidence scoring points and other pieces that were Claude's own ideas: pending Roman's approval.
- `/prices` is reachable through the public tunnel URL: decide local-only or password.
- TBD (Roman, 2026-09-24): fill estimate inputs from the Thumbtack Negotiations API instead of
  asking/guessing, e.g. lead cost (-> Lead.lead_cost) and number of items (-> estimate quantity).
  Which fields exist differs per service (the lead's answers to Thumbtack's service questions), so
  check real API payloads for our services before building. Not in the simulator tests.
- Messages API auth mechanism (`Bearer {{authCode}}` — how is authCode obtained? OAuth flow not
  yet looked at).
- Exact `from` field values on a message (Customer vs Pro vs partner-integration — needed for
  hand-off detection).
- Thumbtack's terms on automated replies — not checked yet.
- `reply-style.md` currently lives at `agent/reply-style.md` (handyman level, shared with manual/
  Chrome-based lead replies). Since `operator/` is meant to be extractable into its own repo,
  this cross-boundary reference needs a decision: move the reply rules into `operator/`, or keep
  a single shared source and accept the dependency. Not decided — no move has been made.

## Reference: LeadWinner (leadwinner.ai, 2026-09-22)
Roman flagged this as a close analog to what we're building — "AI Autoresponder for Yelp,
Thumbtack & Google LSA." Public site findings:
- **Auth is OAuth** ("official OAuth APIs, no password sharing") — likely answers the open
  question above about how Thumbtack's `authCode` is obtained.
- **Hand-off matches our requirement**: "human takes over anytime, bot steps aside."
- Features they have that we don't (not decided whether to build — just noting for later):
  follow-up cadence for silent leads (10 min / 1 hr / 24 hr), 2-way auto-call bridging customer
  and business owner, automatic lead qualification/filtering, SMS + email alerts (vs. our current
  plan of just relying on Thumbtack's own app push notifications).
- Also covers Google LSA and Yelp, consistent with our platform-agnostic design.

## What's built (2026-09-23)
The real agent loop, wired end-to-end and tested with fakes (no real Thumbtack/Anthropic
credentials available, so the live LLM/API calls themselves aren't exercised — everything up to
that boundary is):
- `app/webhooks.py` — idempotency check, lead/session find-or-create, hand-off gate
  (`taken_over`), stop-condition gate (`STOPPED_STATUSES`), then calls the agent.
- `app/agent.py` — the hybrid warm/cold session loop (`ClaudeAgentOptions.resume`), builds all
  tool servers, runs one `query()`, saves the resulting SDK session ID back to the Session record.
- `app/system_prompt.py` — combines `reply-style.md` + `disclosure-whitelist.md` + tool-usage/
  stop-condition instructions into one system prompt.
- `disclosure-whitelist.md` — the whitelist from the "Security: disclosure whitelist" section.
- `app/tools.py` — `send_message` (with a regex price-guard backstop), `get_messages`,
  `record_lead_detail`, `propose_estimate` (draft-only), `estimate_travel`, `check_availability`.
  Each tool's logic is a plain testable function; the `@tool` wrapper just adapts it for the SDK.
- (deleted 2026-10-02, replaced by the catalog) `app/pricing.py` — read `pricing/*.csv`, returned a computed median/range only (never raw
  provider rows) — tested against the real `furniture-assembly.csv` data.
- `app/distance.py` — haversine approximation (placeholder; real driving-distance API not
  decided), origin from server-side env vars, never exposed to the model.
- `app/scheduling/base.py` — `CalendarClient` interface only; no real Google Calendar
  implementation (needs OAuth setup Roman hasn't done).
- `app/db/idempotency.py`, and `Session.sdk_session_id` / `last_activity_at` / `is_warm()` /
  `mark_activity()` added to `app/db/sessions.py`.

Tested directly (temp data dirs, fake `MessagingClient`): tool logic including the price guard,
pricing lookup, distance calc, warm/cold timeout logic, and the full webhook gating flow
(idempotency, hand-off, stop-condition). The live server was booted and confirmed to reach all
the way to the real `ThumbtackMessagingClient`/Agent SDK call, failing only on the expected
missing-credentials boundary (`THUMBTACK_API_BASE_URL` not set) — not a code bug.

**Not built / still open:**
- Real Google Calendar integration (needs OAuth decision).
- Real driving-distance API (needs a maps API key decision).
- Async pricing-research tool (expanding the pricing DB) — not built, still just a manual process.
- Approval interface for estimates/scheduling (still TBD per "Human control / takeover").
- Warm-session timeout duration — currently a 30-minute placeholder.
- (resolved) `reply-style.md` lives in `agent/`; `pricing/` deleted.

## Built: simulator, reply timing, pricing, estimates
- Simulator: `sh/sim.sh` (Chat window: lead messages, `/out` = Roman by hand; Notes window: notes,
  instructions to the agent, `/pause` `/resume`, plain-words stop/continue). Code in `sim/`.
- Reply timing: human-like delays + batching (`app/reply_timing.py`), hold for Roman's decision up to
  10 min (`hold_for_operator`), rewrite if the lead writes mid-reply (LeadWatch).
- Pricing: catalog (seed `db/seed/*.json`, stored in DynamoDB), calculator `app/estimate.py` (compounding
  multipliers, +lead cost, round $5, confidence 1-10, parts included/excluded), Thumbtack import
  `sh/import-thumbtack-prices.sh` (~3,000 rows, coverage report printed by the import),
  `/prices` + `/prices/report` endpoints (grouped, collapsible).
- Estimate flow (Roman, 2026-10-02): rough estimate as soon as the job is known (no link/photos needed —
  nothing reads them yet); re-estimated after every new or changed detail from the lead (link, photos, count,
  size, text). Each new draft supersedes the previous one. Roman approves ("ok") or sets a price; decision recorded.
  Runs in the background (`app/estimator.py`, own small agent with the catalog tools), started alongside
  the reply on every lead message — the reply and its note never wait for it. A new estimate comes as its own
  note; no note when nothing changed. The reply agent never estimates (Roman, 2026-10-02).
  Re-estimate only when the lead says something new that can affect the price — even after Roman sent
  one. Nothing new for the money (time questions, "ok") -> no estimate, no note.
- Background product lookup: results go to Roman's note only, never the lead.
- Tests: 42 unit (`python -m unittest discover tests`), live scenarios `sh/live-estimate-scenarios.sh`.


## Phone channel (Roman, 2026-09-24) — Telegram BUILT (2026-09-25), reworked multi-customer (below)
Talk to the agent during a negotiation from the phone, same as the simulator's Notes window does.
- Push notification on the phone.
- Free text is the main input: Roman types "approve", a price, or any instruction to the agent.
- Buttons are optional extras, never required. Wanted: **Pause** and **Resume**.
  One button, not both: Pause by default, Resume while paused (Roman, 2026-09-25). Shown in two places:
  a status card pinned at the top of the topic (edited in place) and the latest note only.
- Shows status per lead: who is talking to the lead right now — the agent or Roman directly.
- Channel: **Telegram bot** for now (Roman, 2026-09-24). A real mobile app later — keep the channel
  swappable (one operator-channel interface; simulator Notes window and Telegram are implementations).
- Later (Roman, 2026-09-25): Twilio as another channel (calls for strong alerts + talking to the agent);
  own app, replacing Telegram or in parallel.
- Built: see "Multi-customer channels". `app/operator_input.py` is shared with the Notes window.
  Setup: `sh/README.md`.

## Multi-customer channels (Roman, 2026-09-25) — BUILT, not tried with a real bot yet
Build the operator channel the production way, as if connecting a customer (a pro like Roman), and keep
it extendable to SMS and an own app later.
- One bot for the whole product; customers never touch BotFather or IDs.
- Connect = one tap: a connect link `t.me/<bot>?start=<one-time code>` ties the customer's Telegram chat to
  their account. Emulated for now by a script that creates the account and prints the link.
- Private chat with the bot, one topic per lead (Bot API topics in private chats), no group.
- Accounts own leads; a customer only ever sees and controls their own account's leads.
- Telegram updates via webhook in production (polling kept for local/sim runs).
- Channel-neutral core: accounts, channel links, connect codes, who-is-talking status, and operator
  commands are shared; Telegram / SMS / app are adapters on top.
- Built: `app/db/accounts.py`, `app/db/channel_links.py` (links + one-time codes, 24h), `app/channels/`
  (`OperatorChannel` contract, `talker()` status, `Notifier` fan-out + status sync), `app/telegram/`
  (private chat + topics, /start connect, webhook `POST /webhooks/telegram` with secret, polling locally),
  `Lead.account_id` (Thumbtack leads -> `OPERATOR_ACCOUNT_ID` for now), `sh/connect-telegram.sh`,
  `sh/sim.sh --telegram <account_id>`. Replaces the group setup from earlier the same day.
- Adding SMS / app later: a new adapter implementing `OperatorChannel` (notify + sync_all), a connect
  step that redeems a code into a `ChannelLink` (SMS: phone number; app: device/user), and inbound that
  checks the link owns the lead, then calls `app/operator_input.py`. Register it in `Notifier` in
  `app/main.py`. Open for SMS: which lead a reply is about (no topics in SMS).
- Open: mapping each Thumbtack business to its account (per-business Thumbtack connection); the
  BotFather topics setting not verified by hand.

## Readable notes (Roman, 2026-09-25) — BUILT
Notes must be fast to read, in Telegram and all simulator terminals: the lead's message and what we
replied come first, then what Roman must do, then system info. Few words, facts only, no explaining.
Simulators are colored.
- Notes are state, not narration or orders (Roman, 2026-09-25): never retell the chat (it's right above),
  never tell Roman what to do; show what's pending, e.g. "✋ Waiting on you: day & time". Only messages
  are quoted; system info is plain italics.
- Built: `app/note.py` (Note data; lead/sent filled by code word for word, agent adds only short
  status lines; `render_text` for phone channels, `render_terminal` colored for simulators), agent's
  "Note to Roman" rules shortened in `app/system_prompt.py`, short bot/system texts.

## Pinned lead card (Roman, 2026-09-25) — BUILT
The pinned card shows the job, not just the status: who's talking, then service, location, preferred
day, item link, photos (as known; edited silently as details come in). Plus a link to the lead on its
platform ("Open in Thumbtack"; other platforms later) — `Lead.platform_url`.
- Open: where `platform_url` comes from — the Thumbtack lead page URL format / API field isn't confirmed,
  so it's empty until a real negotiation payload is seen. (Card lines: `lead_card()` in
  `app/channels/base.py`, shared by future SMS/app channels.)

## Alarm (Roman, 2026-09-25) — BUILT
When a note waits on Roman ("✋ Waiting on you"), ping him in the lead's topic every 5 s for 5 min, until he
taps "I'm here", sends /here, or writes anything. Pings pile up while it rings and are all deleted when it
stops (deleting each previous ping cut the phone's buzzing — reverted, Roman 2026-09-25). Env: TELEGRAM_ALARM_EVERY_SECONDS, TELEGRAM_ALARM_FOR_SECONDS.
Found while testing: the phone stays silent while Telegram Desktop is active (Telegram's behavior);
brand-new topics show up ~30 s (phone) to ~1 min (desktop) late — early topic creation proposed, not approved yet.
- BotFather "users can create topics" OFF (removes Telegram's "New Chat" item). Side effect: pinned cards
  show in the "All" view, not inside each topic; card is still each topic's first message. Kept as is
  (Roman, 2026-09-25).

## No delay on the first reply (Roman, 2026-09-25) — BUILT
A new lead's first message is answered right away — no human-like wait. All later replies keep the
human delays. (Also gets the lead's Telegram topic up sooner; early topic creation not needed.)

## Per-customer settings (Roman, 2026-09-25) — BUILT
Everything decided about timing and alerting is configurable per customer and changeable in production
without a deploy. Defaults = Roman's decisions (`app/settings.py`); an account stores only what differs.
Settings: reply_delay_min/max_seconds (20/60), reply_max_wait_seconds (120), first_reply_immediate (on),
operator_hold_seconds (600), alarm_every/for_seconds (5/300), session_warm_minutes (30, placeholder).
Change: `sh/account-settings.sh <account> key=value` (customer-facing settings screen later).
- Next (not built): the business profile per customer account. Today it's one profile from env (`BUSINESS_*`,
  `BASE_LATITUDE/LONGITUDE` — see "Prompts and business profile"), i.e. one customer per deployed stage.

## Claude auth: Claude Platform on AWS (Roman, 2026-09-29) — not set up yet
Deploy target is AWS; local testing must keep working. No static key anywhere.
- Why: sim currently runs on Roman's Claude Code subscription login (`ANTHROPIC_API_KEY` empty) —
  fine for testing, not allowed for a product (Agent SDK docs). Console API key skipped.
- Provider: Claude Platform on AWS (Anthropic-operated API, AWS auth, billed via AWS Marketplace).
- Prod: IAM role attached to the service (SigV4 via AWS credential chain).
- Local: `aws login --profile handyagent` (short-lived creds; Identity Center/SSO isn't enabled) +
  `AWS_PROFILE=handyagent-tools` (a profile over that session for tools that can't read `aws login`
  sessions — see `../operator-deploy/README.md`). Not tried with the Claude binary yet.
- Env (`.env`): `CLAUDE_CODE_USE_ANTHROPIC_AWS=1`, `ANTHROPIC_AWS_WORKSPACE_ID`, `AWS_REGION`.
  Agent SDK passes them to the Claude binary — no code change in `app/agent.py`.
- Roman does: Marketplace subscribe (creates a separate Anthropic org), workspace, IAM permissions
  (`aws-external-anthropic` actions) for the prod role and his own login. The stage server roles in
  operator-deploy already allow `aws-external-anthropic:*` (placeholder until verified).
- Verify: run sim with AWS creds and confirm it's not using the Claude Code login.

## DynamoDB (built, 2026-10-02)
- All runtime data in DynamoDB: one table (`operator`), `pk` = record kind (`leads`, `sessions`, `estimates`,
  `accounts`, `channel_links`, `telegram_topics`, `statuses`, `thumbtack_traffic`, catalog `services` /
  `subservices` / `multipliers`…), `sk` = record id. Code: `app/db/records.py` (switch by `DB_BACKEND`),
  `records_dynamo.py`, `dynamo_table.py`; file backend `records_files.py` only for unit tests.
- Local: `sh/dynamo-local.sh` (DynamoDB Local in Docker, port 8001, volume `operator-dynamodb-data`, `reset`
  wipes it); started by `run.sh`, `sim.sh`, `chat.sh`. A fresh table gets seeded.
- Seed: `db/seed/` is the only seed folder (pricing catalog). `sh/dynamo-seed.sh` loads it into whatever
  DynamoDB the env points at — local or a stage (deploy sets table + AWS creds).
- `.env` is loaded by uvicorn (`--env-file`), not on import — tests never touch DynamoDB (moto for its tests).
- Old file records (`db/records/`) imported, then deleted (Roman, 2026-10-02).

## Prompts and business profile (Roman, 2026-10-02) — BUILT
- All prompt text lives in `agent/*.md`, loaded by `app/prompts.py` — none in Python.
- The customer's business profile (owner, business name, services, service area) comes from env
  (`BUSINESS_*`, `app/business.py`), filled into the prompts. Missing value -> error, never a blank to a lead.

## Future: user signup flow (draft, Roman 2026-10-03) — not built
Now: one account, set in env. Later: many users sign up.
Assumption: Thumbtack gives only "log in + approve" — no business picker, no API to find the connected
business, no webhook registration by API in production.
1. Sign up on handyagent.dev → Handy Agent account.
2. We show the user's own webhook URL `https://api.handyagent.dev/webhooks/thumbtack/<account-key>`
   (+ basic-auth credentials). The user adds it at thumbtack.com/pro/webhooks/list, events: leads +
   messages — the same self-serve setup Roman did.
3. "Connect Thumbtack" — part of signup; signup isn't done without it. OAuth login + approve on
   Thumbtack (the user grants Handy Agent scopes: read leads, read/send messages, `offline_access`) →
   back to our callback. Tokens stored under the user's account; this is the first API connection
   and is needed to send replies. Keys: one Handy Agent key set (prod + staging) for all users — never
   per user.
4. The business is learned from the first webhook delivery: the payload carries
   `business{businessID, displayName}` (seen in real deliveries). Until then: "waiting for first lead".
5. Business profile + settings, Telegram connect, plan/payment.
6. Live: webhook → account from the URL key → agent replies with that account's tokens.

### Investigate (Thumbtack)
- What the OAuth consent screen shows; can a pro with several businesses pick one.
- An API call that returns the connected user/business after OAuth.
- Webhook registration by API in production (docs show it for staging).
- Can one pro have two active logins (e.g. local + a stage).
- Self-serve webhook auth options (Roman picked "none"; basic auth?).
