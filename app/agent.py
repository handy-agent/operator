# What it does: The actual agent loop — one call per webhook event. Builds the hybrid
#   warm/rebuild session (decided 2026-09-23), assembles all tools, and runs one Agent
#   SDK query. Does NOT decide whether to run at all (taken_over / stop-condition / idempotency
#   gating happens in app/webhooks.py, before this is called) — this module just runs a turn.
# When it runs: Called by app/webhooks.py for each handled, non-gated webhook event.
# What calls it: app/webhooks.py.
from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query

from . import note as note_module, prompts, settings, system_prompt, tools
from .db import estimates, held_replies, sessions
from .messaging.base import MessagingClient
from .scheduling.base import CalendarClient

# SDK MCP tools are only permitted under their full "mcp__<server>__<tool>" names — bare tool
# names are silently not matched and every call is denied.
ALLOWED_TOOLS = [
    "mcp__messaging__send_message",
    "mcp__messaging__hold_for_operator",
    "mcp__messaging__get_messages",
    "mcp__lead__record_lead_detail",
    "mcp__travel__estimate_travel",
    "mcp__scheduling__check_availability",
]
# Only on the operator's instruction turns (see run_agent_turn).
CONTROL_TOOLS = ["mcp__control__pause_lead", "mcp__control__resume_lead"]
# Taken away while the lead is paused (decided 2026-09-25): the operator is talking to the lead himself,
# so his messages are a conversation with the agent only — nothing reaches the lead until /resume.
LEAD_FACING_TOOLS = {"mcp__messaging__send_message", "mcp__messaging__hold_for_operator"}


async def run_agent_turn(
    session_id: str,
    lead_id: str,
    incoming_text: str,
    messaging_client: MessagingClient,
    calendar_client: CalendarClient | None = None,
    from_operator: bool = False,
    lead_texts: list[str] | None = None,
) -> note_module.Note | None:
    """Runs one turn. Returns the note to the operator: `lead_texts` (the lead's messages this turn)
    and what was sent to the lead, both word for word, plus the agent's own short status lines.

    from_operator=True means incoming_text is the operator's own instruction (private channel),
    not a lead message: it's trusted, and any price in it becomes sendable this turn.
    """
    session = sessions.find(session_id)
    if session is None:
        raise ValueError(f"No session {session_id}")

    if from_operator:
        # The operator answered, so any held "let me check" fallback is no longer needed.
        held_replies.clear(session_id)
        incoming_text = prompts.section("turn-notices", "operator-instruction", TEXT=incoming_text)
        if session.taken_over:
            incoming_text += "\n\n" + prompts.section("turn-notices", "paused")
        approved_amounts = tools.instruction_amounts(incoming_text)
        # "Approve" with no number means the latest draft's suggested price.
        if (draft := estimates.latest_draft(session_id)) and draft.suggested is not None:
            approved_amounts |= {str(draft.suggested)}
            # Estimates are drafted in the background (app/estimator.py), so the agent learns the number here.
            incoming_text += "\n\n" + prompts.section("turn-notices", "latest-price", SUGGESTED=str(draft.suggested),
                                                        PRICE_TEXT=draft.price_text or "")
    else:
        incoming_text = prompts.section("turn-notices", "lead-messages", TEXT=incoming_text)
        approved_amounts = frozenset()

    thread = await messaging_client.get_messages(session_id)
    watch = tools.LeadWatch(thread)
    # Decided in code, not by the model: it misjudged "first message" whenever its first reply was
    # held or the lead opened with several texts.
    if not any(m.sender in ("agent", "operator") for m in thread):
        incoming_text += "\n\n" + prompts.section("turn-notices", "first-message")

    warm = sessions.is_warm(session, int(settings.for_lead(lead_id)["session_warm_minutes"] * 60))
    resume_id = session.sdk_session_id if warm else None

    if not warm and session.sdk_session_id is not None:
        # Rebuilding after a timeout — include the thread in case something happened while no
        # live session was held (missed webhook, the owner replying manually, etc).
        history = "\n".join(f"[{m.sender} @ {m.sent_at}] {m.text}" for m in thread)
        prompt = prompts.section("turn-notices", "session-rebuilt", HISTORY=history, TEXT=incoming_text)
    else:
        prompt = incoming_text

    context_header = prompts.section("turn-notices", "lead-id", LEAD_ID=lead_id) + "\n\n"

    mcp_servers = {
        "messaging": tools.build_messaging_tools(messaging_client, approved_amounts, watch),
        "lead": tools.build_lead_tools(),
        "travel": tools.build_travel_tools(),
        "scheduling": tools.build_scheduling_tools(calendar_client),
    }
    allowed_tools = ALLOWED_TOOLS
    if from_operator:
        mcp_servers["control"] = tools.build_control_tools()
        allowed_tools = allowed_tools + CONTROL_TOOLS
    if session.taken_over:
        allowed_tools = [t for t in allowed_tools if t not in LEAD_FACING_TOOLS]
    options = ClaudeAgentOptions(
        system_prompt=system_prompt.build_system_prompt(),
        mcp_servers=mcp_servers,
        allowed_tools=allowed_tools,
        disallowed_tools=sorted(LEAD_FACING_TOOLS) if session.taken_over else [],
        resume=resume_id,
        # No filesystem settings (CLAUDE.md, ~/.claude): the agent sees only what we pass, same locally and on AWS.
        setting_sources=[],
    )

    sdk_session_id: str | None = None
    note_to_operator: str | None = None
    async for message in query(prompt=context_header + prompt, options=options):
        if isinstance(message, ResultMessage):
            sdk_session_id = message.session_id
            note_to_operator = message.result

    if sdk_session_id is not None:
        sessions.mark_activity(session_id, sdk_session_id)

    before = {m.message_id for m in thread}
    sent = [m.text for m in await messaging_client.get_messages(session_id)
            if m.sender == "agent" and m.message_id not in before]
    if not (note_to_operator or sent):
        return None
    source = "instruction" if from_operator else "lead"
    return note_module.from_agent(source, note_to_operator, lead_texts or [], sent)
