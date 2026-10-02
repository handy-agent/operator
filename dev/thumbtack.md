# Thumbtack adapter

## Flow
1. Thumbtack sends lead messages to our self-serve webhook: `POST /webhooks/thumbtack` (`app/main.py`,
   parsed by `message_from_event()` in `app/webhooks.py`). Messages only so far; leads events to be added.
2. The agent (Claude Agent SDK, `app/agent.py`) replies per `agent/reply-style.md`, after human-like
   delays (`app/reply_timing.py`). Detail-gathering only; price/timing need Roman's yes.
3. Replies go out through the Partner Messages API (`app/messaging/thumbtack.py`) — needs the partner
   keys + OAuth flow (not built yet, see `STATUS.md`).
4. Roman gets notes on Telegram, one topic per lead (`sh/README.md` "Telegram"); a price suggestion comes
   in its own note from the background estimate (`app/estimator.py`).

## Record
- Leads, sessions, estimates and every Thumbtack exchange (traffic log) in DynamoDB — see `app/db/`.

## Open
- Thumbtack's terms on automated replies: not checked yet.
