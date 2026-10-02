# What it does: Wraps everything the agent is allowed to *do* as Claude Agent SDK tools —
#   messaging, estimate drafting, lead-detail recording, travel distance, and calendar
#   availability. The agent calls these itself rather than app code driving it directly
#   (the owner's framing, 2026-09-22: "messaging will be our tools", extended 2026-09-23 to the
#   rest of the loop). Each builder takes its dependency as an argument (MessagingClient,
#   CalendarClient, ...) so swapping implementations later doesn't change this file.
#
#   Each tool's real logic lives in a plain `_*_impl` function below, independently testable
#   without going through the MCP protocol; the `@tool`-decorated closures in build_*_tools()
#   just adapt args/return shape for the SDK.
# When it runs: build_*_tools() are called once per agent turn to assemble
#   ClaudeAgentOptions.mcp_servers.
# What calls it: app/agent.py.
import asyncio
import os
import re

from claude_agent_sdk import McpSdkServerConfig, create_sdk_mcp_server, tool

from . import business, catalog, distance, prompts, settings
from .estimate import EstimateInput, estimate
from .db import estimates, held_replies, leads, sessions
from .messaging.base import Message, MessagingClient
from .scheduling.base import CalendarClient

# Backstop per REQUIREMENTS.md "Security: prompt injection" — price must go through
# propose_estimate (draft, needs the owner's approval), never straight through send_message, no
# matter what the conversation says. This is a structural check, not a suggestion to the model.
_PRICE_PATTERN = re.compile(r"\$\s?\d|\bdollars?\b", re.IGNORECASE)
_PRICE_AMOUNT = re.compile(r"\$\s?(\d[\d,]*(?:\.\d+)?)")


def price_amounts(text: str) -> frozenset[str]:
    """Dollar amounts in text, normalized ("$1,100" -> "1100"). Used to allow exactly the prices
    the owner himself gave in an instruction, and nothing else."""
    return frozenset(m.replace(",", "") for m in _PRICE_AMOUNT.findall(text))


_ANY_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def instruction_amounts(text: str) -> frozenset[str]:
    """Amounts the operator approved in an instruction. He may write "100" without a "$", so every
    number counts — the instruction is trusted, and this only widens what the agent may send."""
    return frozenset(m.replace(",", "") for m in _ANY_NUMBER.findall(text))


def _text_result(text: str, is_error: bool = False) -> dict:
    result = {"content": [{"type": "text", "text": text}]}
    if is_error:
        result["is_error"] = True
    return result


def _message_key(message: Message) -> str:
    return message.message_id or f"{message.sent_at}|{message.text}"


class LeadWatch:
    """Lead messages the agent has already seen this turn. Right before anything goes out, lead
    messages that arrived meanwhile are shown to the agent instead, so it answers everything in one
    reply — like a person who reads the new text before hitting send."""

    def __init__(self, messages: list[Message]) -> None:
        self._seen = {_message_key(m) for m in messages if m.sender == "lead"}

    async def new_lead_messages(self, client: MessagingClient, session_id: str) -> list[Message]:
        new = [m for m in await client.get_messages(session_id) if m.sender == "lead" and _message_key(m) not in self._seen]
        self._seen.update(_message_key(m) for m in new)
        return new


async def _refuse_if_lead_wrote(watch: "LeadWatch | None", client: MessagingClient, session_id: str) -> dict | None:
    if watch is None:
        return None
    new = await watch.new_lead_messages(client, session_id)
    if not new:
        return None
    texts = "\n".join(f"- {m.text}" for m in new)
    return _text_result(
        prompts.section("tool-results", "lead-wrote-meanwhile", TEXTS=texts),
        is_error=True,
    )


async def _send_message_impl(
    client: MessagingClient,
    session_id: str,
    text: str,
    approved_amounts: frozenset[str] = frozenset(),
    watch: LeadWatch | None = None,
) -> dict:
    # A price is only sendable if every amount in it is one the owner gave in this turn's instruction.
    if _PRICE_PATTERN.search(text) and not (price_amounts(text) and price_amounts(text) <= approved_amounts):
        return _text_result(
            prompts.section("tool-results", "price-blocked"),
            is_error=True,
        )
    # The sign-off goes on the very first message to a lead only; repeating it reads like a bot (decided 2026-09-23).
    if business.profile()["BUSINESS_NAME"] in text and any(m.sender in ("agent", "operator") for m in await client.get_messages(session_id)):
        return _text_result(
            prompts.section("tool-results", "sign-off-repeated"),
            is_error=True,
        )
    if refusal := await _refuse_if_lead_wrote(watch, client, session_id):
        return refusal
    await client.send_message(session_id, text)
    if approved_amounts and (amounts := price_amounts(text) & approved_amounts):
        # The owner's price went out on their instruction: remember what they decided vs. what was suggested.
        estimates.record_decision(session_id, float(max(amounts, key=float)))
    return _text_result("sent")


def hold_seconds(session_id: str) -> float:
    # How long a held reply waits for the customer before the fallback goes out: their setting
    # (app/settings.py). The simulator overrides it with OPERATOR_HOLD_SECONDS (sim/chat.py).
    if override := os.getenv("OPERATOR_HOLD_SECONDS"):
        return float(override)
    return float(settings.for_lead(session_id)["operator_hold_seconds"])


async def _hold_for_operator_impl(
    client: MessagingClient, session_id: str, fallback_text: str, watch: LeadWatch | None = None
) -> dict:
    if _PRICE_PATTERN.search(fallback_text):
        return _text_result("error: the fallback text can't contain a price.", is_error=True)
    if refusal := await _refuse_if_lead_wrote(watch, client, session_id):
        return refusal
    hold_id = held_replies.hold(session_id, fallback_text)
    delay = hold_seconds(session_id)
    asyncio.get_running_loop().create_task(_send_fallback_later(client, session_id, hold_id, delay))
    return _text_result(
        prompts.section("tool-results", "held", SECONDS=str(int(delay)))
    )


async def _send_fallback_later(client: MessagingClient, session_id: str, hold_id: str, delay: float) -> None:
    await asyncio.sleep(delay)
    fallback_text = held_replies.take_if_current(session_id, hold_id)
    session = sessions.find(session_id)
    if fallback_text is not None and not (session and session.taken_over):
        await client.send_message(session_id, fallback_text)


async def _get_messages_impl(client: MessagingClient, session_id: str) -> dict:
    messages = await client.get_messages(session_id)
    lines = [f"[{m.sender} @ {m.sent_at}] {m.text}" for m in messages]
    return _text_result("\n".join(lines) or "(no messages)")


# Only these Lead fields are the agent's to fill. status/timestamps/lead_id are system-owned —
# status drives the stop conditions, so the agent must never be able to change it.
AGENT_WRITABLE_LEAD_FIELDS = (
    "name", "phone", "service", "location", "item_link", "photos", "preferred_day", "state",
)


async def _record_lead_detail_impl(lead_id: str, field: str, value: str) -> dict:
    lead = leads.find(lead_id)
    if lead is None:
        return _text_result("error: lead not found", is_error=True)
    if field not in AGENT_WRITABLE_LEAD_FIELDS:
        return _text_result(
            f"error: unknown field '{field}'. Allowed: {', '.join(AGENT_WRITABLE_LEAD_FIELDS)}",
            is_error=True,
        )
    setattr(lead, field, value)
    leads.save(lead)
    return _text_result("saved")


async def _propose_estimate_impl(
    lead_id: str,
    subservice_id: str,
    quantity: float = 1,
    options: dict[str, str] | None = None,
    distance_miles: float | None = None,
) -> dict:
    lead = leads.find(lead_id)
    if lead is None:
        return _text_result("error: lead not found", is_error=True)
    # Rough estimate from the start; re-estimated as details come in (decided 2026-10-02).
    rough = not (lead.item_link or lead.photos)
    if catalog.subservice(subservice_id) is None:
        return _text_result(f"error: unknown subservice '{subservice_id}'. Use search_catalog to find it.", is_error=True)
    result = estimate(
        EstimateInput(
            subservice_id=subservice_id,
            quantity=quantity,
            options=options or {},
            state=lead.state,
            distance_miles=distance_miles,
            lead_cost=lead.lead_cost,
        )
    )
    # Same job, same price as the newest estimate (even one the owner already decided): nothing new to say.
    previous = estimates.latest(lead_id)
    if previous and (previous.service, previous.suggested, previous.rough) == (subservice_id, result.suggested, rough):
        return _text_result(f"unchanged: same as estimate {previous.estimate_id} ({previous.status}). No new draft.")
    draft = estimates.create(
        lead_id=lead_id, service=subservice_id, price_text=result.summary(), source="catalog",
        suggested=result.suggested, confidence=result.confidence, rough=rough,
    )
    label = "Rough (no link/photos, size not checked)" if rough else "Draft"
    return _text_result(
        prompts.section("tool-results", "estimate-drafted", LABEL=label, ID=draft.estimate_id, SUMMARY=result.summary())
    )


def _describe_subservice(s: dict) -> str:
    market = s.get("market") or {}
    return (
        f"{s['id']} ({s['name']}; quantity = {_QUANTITY_MEANING[s['pricing']['model']]}"
        + "".join(f"; {g['id']}: {'/'.join(o['id'] for o in g['options'])}" for g in s.get("option_groups", []))
        + (f"; market ${market['low']}-{market['high']}" if market else "")
        + ")"
    )


def _stem(word: str) -> str:
    # "assemble"/"assembly", "mounting"/"mount": compare on the first 5 letters of longer words.
    return word[:5] if len(word) > 5 else word


async def _search_catalog_impl(query: str, limit: int = 8) -> dict:
    stems = [_stem(w) for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 2]
    scored = []
    for s in catalog.subservices():
        if s.get("summary"):  # a page's "low-end / national average" row, not a job
            continue
        name = s["name"].lower()
        other = f"{s['id']} {s['service_id']}".replace("_", " ")
        # Matches in the job's own name count double; shorter names (the job itself, not a detail row) win ties.
        matches = sum(2 if st in name else 1 if st in other else 0 for st in stems)
        score = matches - len(name) / 1000
        if matches:
            scored.append((score, not s.get("imported"), s))  # hand-curated first on ties
    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
    if not scored:
        return _text_result(prompts.section("tool-results", "catalog-no-match"))
    return _text_result("\n".join(_describe_subservice(s) for _, _, s in scored[:limit]))


_QUANTITY_MEANING = {"per_item": "number of items", "flat": "number of jobs", "hourly": "hours", "per_unit": "units"}


async def _estimate_travel_impl(destination_lat: float, destination_lon: float) -> dict:
    try:
        result = distance.estimate_travel(destination_lat, destination_lon)
    except RuntimeError as e:
        return _text_result(f"error: {e}", is_error=True)
    return _text_result(f"{result.straight_line_miles} miles ({result.note})")


async def _check_availability_impl(client: CalendarClient | None, day: str) -> dict:
    if client is None:
        return _text_result("Calendar isn't connected yet — cannot check availability.")
    slots = await client.free_slots(day)
    lines = [f"{s.start} - {s.end}" for s in slots]
    return _text_result("\n".join(lines) or "no free slots")


def build_messaging_tools(
    client: MessagingClient, approved_amounts: frozenset[str] = frozenset(), watch: LeadWatch | None = None
) -> McpSdkServerConfig:
    @tool(
        "send_message",
        prompts.section("tools", "send_message"),
        {"session_id": str, "text": str},
    )
    async def send_message(args: dict) -> dict:
        return await _send_message_impl(client, args["session_id"], args["text"], approved_amounts, watch)

    @tool(
        "hold_for_operator",
        prompts.section("tools", "hold_for_operator"),
        {"session_id": str, "fallback_text": str},
    )
    async def hold_for_operator(args: dict) -> dict:
        return await _hold_for_operator_impl(client, args["session_id"], args["fallback_text"], watch)

    @tool(
        "get_messages",
        prompts.section("tools", "get_messages"),
        {"session_id": str},
    )
    async def get_messages(args: dict) -> dict:
        return await _get_messages_impl(client, args["session_id"])

    return create_sdk_mcp_server(name="messaging", tools=[send_message, hold_for_operator, get_messages])


def build_lead_tools() -> McpSdkServerConfig:
    @tool(
        "record_lead_detail",
        prompts.section("tools", "record_lead_detail"),
        {"lead_id": str, "field": str, "value": str},
    )
    async def record_lead_detail(args: dict) -> dict:
        return await _record_lead_detail_impl(args["lead_id"], args["field"], args["value"])

    return create_sdk_mcp_server(name="lead", tools=[record_lead_detail])


def build_estimate_tools() -> McpSdkServerConfig:
    @tool(
        "propose_estimate",
        prompts.section("tools", "propose_estimate"),
        {
            "type": "object",
            "properties": {
                "lead_id": {"type": "string"},
                "subservice_id": {"type": "string"},
                "quantity": {"type": "number", "description": "Items, hours, or units (see the subservice)"},
                "options": {"type": "object", "description": "Option group id -> chosen option id, only if known",
                            "additionalProperties": {"type": "string"}},
                "distance_miles": {"type": "number", "description": "Only if known (estimate_travel)"},
            },
            "required": ["lead_id", "subservice_id", "quantity"],
        },
    )
    async def propose_estimate(args: dict) -> dict:
        return await _propose_estimate_impl(
            args["lead_id"], args["subservice_id"], args["quantity"], args.get("options"), args.get("distance_miles")
        )

    @tool(
        "search_catalog",
        prompts.section("tools", "search_catalog"),
        {"query": str},
    )
    async def search_catalog(args: dict) -> dict:
        return await _search_catalog_impl(args["query"])

    return create_sdk_mcp_server(name="estimate", tools=[propose_estimate, search_catalog])


def build_travel_tools() -> McpSdkServerConfig:
    @tool(
        "estimate_travel",
        prompts.section("tools", "estimate_travel"),
        {"destination_lat": float, "destination_lon": float},
    )
    async def estimate_travel(args: dict) -> dict:
        return await _estimate_travel_impl(args["destination_lat"], args["destination_lon"])

    return create_sdk_mcp_server(name="travel", tools=[estimate_travel])


def build_scheduling_tools(client: CalendarClient | None) -> McpSdkServerConfig:
    @tool(
        "check_availability",
        prompts.section("tools", "check_availability"),
        {"day": str},
    )
    async def check_availability(args: dict) -> dict:
        return await _check_availability_impl(client, args["day"])

    return create_sdk_mcp_server(name="scheduling", tools=[check_availability])


async def _pause_lead_impl(session_id: str) -> dict:
    sessions.mark_taken_over(session_id)
    return _text_result("paused: no automatic replies on this lead until the operator resumes it")


async def _resume_lead_impl(session_id: str) -> dict:
    sessions.resume(session_id)
    return _text_result("resumed: automatic replies are back on from the next lead message")


def build_control_tools() -> McpSdkServerConfig:
    """Pause/resume the agent on a lead. Only given to the agent on the operator's own
    instruction turns — a lead message can never pause or resume anything."""

    @tool(
        "pause_lead",
        prompts.section("tools", "pause_lead"),
        {"session_id": str},
    )
    async def pause_lead(args: dict) -> dict:
        return await _pause_lead_impl(args["session_id"])

    @tool(
        "resume_lead",
        prompts.section("tools", "resume_lead"),
        {"session_id": str},
    )
    async def resume_lead(args: dict) -> dict:
        return await _resume_lead_impl(args["session_id"])

    return create_sdk_mcp_server(name="control", tools=[pause_lead, resume_lead])
