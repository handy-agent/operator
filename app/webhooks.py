# What it does: Handles an incoming Thumbtack webhook event end-to-end: idempotency check,
#   session/lead find-or-create (the owner's rule, 2026-09-22: new negotiation ID -> create a lead;
#   existing -> continue that session), stop-condition and hand-off gating, then runs the agent
#   turn if none of the gates block it.
# When it runs: Called by main.py's POST /webhooks/thumbtack route for every event delivered.
# What calls it: app/main.py.
#
# Payload: a real MessageCreatedV4 delivery (2026-09-30) is {"event": {"eventType", ...},
# "data": {messageID, negotiationID, customer{customerID, displayName}, business{businessID,
# displayName}, from, text, sentAt}}. main.py unwraps it with message_from_event() and passes `data`
# here. Other event types (e.g. NegotiationCreatedV4) not seen yet — logged and skipped.
# THUMBTACK_API_BASE_URL / THUMBTACK_API_TOKEN must be set for ThumbtackMessagingClient to work —
# see app/messaging/thumbtack.py.
import asyncio
import json
import logging
from collections import defaultdict
from collections.abc import Callable
from typing import Any

from . import agent, estimator, item_lookup, settings
from .db import accounts, estimates, held_replies, idempotency, leads, sent_messages, sessions, statuses
from .messaging.base import MessagingClient
from .messaging.thumbtack import ThumbtackMessagingClient
from .note import Note
from .reply_timing import ReplyScheduler

# Per REQUIREMENTS.md "Stop conditions": once a negotiation is scheduled or further along,
# there's nothing left to negotiate. Thumbtack's own job-status vocabulary (confirmed from the
# Partner Platform docs) — not yet wired to a real status-refresh mechanism, so Lead.status only
# reaches these values once something actually sets it (not built yet).
STOPPED_STATUSES = {"appt_scheduled", "job_complete", "invoice_paid", "customer_cancel", "pro_cancel"}


def message_from_event(body: dict[str, Any]) -> dict[str, Any] | None:
    """The message inside a Thumbtack webhook delivery, or None for any other event type."""
    if (body.get("event") or {}).get("eventType") != "MessageCreatedV4":
        return None
    return body.get("data") or {}


async def handle_thumbtack_event(
    payload: dict[str, Any],
    messaging_client: MessagingClient | None = None,
    scheduler: ReplyScheduler | None = None,
    account_id: str | None = None,
) -> dict[str, Any]:
    """Gates the event, then either hands the text to `scheduler` (human-like, batched reply —
    what production and the two-window simulator use) or, with no scheduler, runs the agent now."""
    negotiation_id = payload.get("negotiationID")
    if not negotiation_id:
        return {"handled": False, "reason": "missing negotiationID"}

    event_id = payload.get("messageID") or f"{negotiation_id}:{payload.get('sentAt', '')}"
    if idempotency.already_handled(event_id):
        return {"handled": False, "reason": "duplicate event", "event_id": event_id}

    lead, lead_is_new = leads.find_or_create(
        negotiation_id,
        name=(payload.get("customer") or {}).get("displayName"),  # Thumbtack calls the lead "customer"
        account_id=account_id or accounts.for_platform_event(payload),
    )
    session, _ = sessions.find_or_create(negotiation_id, lead_id=lead.lead_id)

    if lead_is_new:
        statuses.record(lead.lead_id, "lead_created", "first webhook event for this negotiation")

    # Pro-side message (the owner's rule, 2026-09-23): the agent's own echo is ignored; anything else is
    # the operator replying by hand, which pauses the agent on this lead until they explicitly resume it.
    # NOTE: the "from" values are unverified — confirm against a real webhook delivery.
    if payload.get("from", "Customer") != "Customer":
        idempotency.mark_handled(event_id)
        if payload.get("text", "") in sent_messages.texts(negotiation_id):
            return {"handled": False, "reason": "own message echo"}
        sessions.mark_taken_over(session.session_id)
        held_replies.clear(session.session_id)
        statuses.record(lead.lead_id, "taken_over", "operator replied by hand")
        return {"handled": True, "lead_id": lead.lead_id, "taken_over": True, "reason": "operator replied by hand"}

    result = {
        "handled": True,
        "lead_id": lead.lead_id,
        "session_id": session.session_id,
        "lead_is_new": lead_is_new,
        "taken_over": session.taken_over,
    }

    if session.taken_over:
        statuses.record(lead.lead_id, "event_received_while_taken_over")
        idempotency.mark_handled(event_id)
        return result

    if lead.status in STOPPED_STATUSES:
        statuses.record(lead.lead_id, "event_received_while_stopped", lead.status)
        idempotency.mark_handled(event_id)
        return {**result, "stopped_status": lead.status}

    statuses.record(lead.lead_id, "event_received")
    idempotency.mark_handled(event_id)

    if scheduler is not None:
        immediate = lead_is_new and bool(settings.for_lead(negotiation_id)["first_reply_immediate"])
        scheduler.add(negotiation_id, payload.get("text", ""), immediate=immediate)
        return {**result, "scheduled": True}

    # Simulator (sim/) passes a fake client; real webhooks use Thumbtack.
    note_to_operator = await run_batched_turn(
        negotiation_id, [payload.get("text", "")], messaging_client or ThumbtackMessagingClient()
    )
    return {**result, "note_to_operator": note_to_operator}


def make_item_lookup(messaging_client: MessagingClient, on_note: Callable[[Note], None]) -> Callable[[str, str], None]:
    """Returns start_lookup(lead_id, description): searches for the product in the background and puts
    what it found in a note to the operator. Nothing goes to the lead (decided 2026-09-24)."""

    def start_lookup(lead_id: str, description: str) -> None:
        asyncio.get_running_loop().create_task(_lookup(lead_id, description))

    async def _lookup(lead_id: str, description: str) -> None:
        try:
            result = await item_lookup.look_up(description)
        except Exception:  # a background task's error would otherwise vanish silently
            logging.getLogger("operator").exception("Item lookup failed for %s", lead_id)
            on_note(Note(source="lookup", lines=[f"Lookup failed: {description} (see app log)"]))
            return
        on_note(item_lookup.as_note(description, result))

    return start_lookup


# One estimate at a time per lead: a second request waits and then sees the first one's draft.
_estimate_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


def make_estimator(messaging_client: MessagingClient, on_note: Callable[[Note], None]) -> Callable[[str], None]:
    """Returns start_estimate(lead_id): drafts a price suggestion in the background (app/estimator.py) and
    puts it in its own note to the operator, only when there's a new one. Never delays the reply turn and
    never reaches the lead (decided 2026-10-02)."""

    def start_estimate(lead_id: str) -> None:
        asyncio.get_running_loop().create_task(_estimate(lead_id))

    async def _estimate(lead_id: str) -> None:
        async with _estimate_locks[lead_id]:
            before = estimates.latest(lead_id)
            try:
                await estimator.run(lead_id, messaging_client)
            except Exception:  # a background task's error would otherwise vanish silently
                logging.getLogger("operator").exception("Estimate failed for %s", lead_id)
                on_note(Note(source="estimate", lines=["Estimate failed (see app log)"]))
                return
            after = estimates.latest(lead_id)
            if after is not None and (before is None or after.estimate_id != before.estimate_id):
                on_note(estimator.as_note(after))

    return start_estimate


async def run_batched_turn(
    negotiation_id: str,
    texts: list[str],
    messaging_client: MessagingClient,
    start_lookup: Callable[[str, str], None] | None = None,
    start_estimate: Callable[[str], None] | None = None,
) -> Note | None:
    """One agent turn answering every lead message that arrived since the last one. Gating is
    re-checked here because the operator may have taken over while the reply was waiting."""
    session = sessions.find(negotiation_id)
    lead = leads.find(negotiation_id)
    if session is None or lead is None or session.taken_over or lead.status in STOPPED_STATUSES:
        return None
    # Already answered: the previous turn saw these messages arrive before it sent (LeadWatch in
    # app/tools.py) and covered them in its reply, or the operator replied by hand.
    thread = await messaging_client.get_messages(negotiation_id)
    if thread and thread[-1].sender != "lead":
        return None
    # The lead said something new: (re)estimate alongside the reply, never before it.
    if start_estimate:
        start_estimate(negotiation_id)
    note = await agent.run_agent_turn(
        session_id=session.session_id,
        lead_id=lead.lead_id,
        incoming_text="\n\n".join(texts),
        messaging_client=messaging_client,
        lead_texts=texts,
    )
    # Decided in code, not left to the agent (it skipped the lookup when it was optional): once the
    # job is known but there's no link or photos yet, look the product up in the background, once.
    lead = leads.find(negotiation_id)
    if start_lookup and lead and lead.service and not (lead.item_link or lead.photos or lead.item_lookup_started):
        lead.item_lookup_started = True
        leads.save(lead)
        start_lookup(lead.lead_id, lead.service)
    return note
