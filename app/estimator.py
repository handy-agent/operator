# What it does: Background estimate (decided 2026-10-02). A small agent with only the catalog tools reads
#   the lead's conversation and saved details and drafts a price suggestion for the operator: rough from
#   the first message, redone whenever the lead adds or changes something that affects the price. Runs
#   alongside the reply turn, so the lead's reply and the operator's note never wait for it. The draft
#   goes to the operator only (a separate note, see app/webhooks.py make_estimator) — never to the lead.
# When it runs: On every batch of lead messages (app/webhooks.py run_batched_turn).
# What calls it: app/webhooks.py.
from claude_agent_sdk import ClaudeAgentOptions, query

from . import prompts, tools
from .db import estimates, leads
from .messaging.base import MessagingClient
from .note import Note

ALLOWED_TOOLS = ["mcp__estimate__search_catalog", "mcp__estimate__propose_estimate"]


def _prompt(lead_id: str, thread_text: str, details: dict, previous: estimates.Estimate | None) -> str:
    saved = ", ".join(f"{k}={v}" for k, v in details.items() if v) or "none"
    if previous is None:
        before = "none"
    else:
        decided = f", owner sent ${previous.approved_price:g}" if previous.approved_price is not None else ""
        before = f"{previous.service}: {previous.price_text} (rough={previous.rough}, {previous.status}{decided})"
    return prompts.section("turn-notices", "estimate-request", LEAD_ID=lead_id, SAVED=saved, PREVIOUS=before,
                           CONVERSATION=thread_text)


async def run(lead_id: str, messaging_client: MessagingClient) -> None:
    """Drafts a new estimate if the job is clear and something changed (propose_estimate writes it)."""
    lead = leads.find(lead_id)
    if lead is None:
        return
    thread = await messaging_client.get_messages(lead_id)
    thread_text = "\n".join(f"[{m.sender}] {m.text}" for m in thread)
    details = {f: getattr(lead, f) for f in ("service", "location", "item_link", "photos", "state")}
    options = ClaudeAgentOptions(
        system_prompt=prompts.text("estimator"),
        mcp_servers={"estimate": tools.build_estimate_tools()},
        allowed_tools=ALLOWED_TOOLS,
        max_turns=6,
        setting_sources=[],  # no filesystem settings, see app/agent.py
    )
    async for _ in query(prompt=_prompt(lead_id, thread_text, details, estimates.latest(lead_id)), options=options):
        pass


def as_note(draft: estimates.Estimate) -> Note:
    """For the operator only; nothing goes to the lead."""
    label = "Rough (no link/photos, size not checked): " if draft.rough else ""
    return Note(source="estimate", price=f"{label}{draft.price_text}")
