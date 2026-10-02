# What it does: What the operator (the owner) types to the agent about one lead, whatever the channel:
#   /pause, /resume, or an instruction (trusted; a price in it is approved) that runs an agent turn.
#   One place, so the simulator's Notes window and Telegram behave the same.
# When it runs: Every time the operator sends something about a lead.
# What calls it: sim/notes.py, sim/telegram.py, app/main.py.
from . import agent
from .db import sessions
from .messaging.base import MessagingClient
from .note import Note, system

NO_LEAD = "No lead yet."
PAUSED = "⏸ Paused. You're talking."
RESUMED = "▶️ Resumed. Agent replies to the next lead message."


def control_command(session_id: str, text: str) -> str | None:
    """Applies /pause or /resume and returns what to tell the operator; None if text isn't one."""
    if text not in ("/pause", "/resume"):
        return None
    if sessions.find(session_id) is None:
        return NO_LEAD
    if text == "/pause":
        sessions.mark_taken_over(session_id)
        return PAUSED
    sessions.resume(session_id)
    return RESUMED


async def run_instruction(session_id: str, text: str, messaging_client: MessagingClient) -> Note | None:
    """Runs the agent on the operator's instruction. Returns the note to the operator."""
    session = sessions.find(session_id)
    if session is None:
        return system(NO_LEAD)
    return await agent.run_agent_turn(
        session_id=session.session_id,
        lead_id=session.lead_id,
        incoming_text=text,
        messaging_client=messaging_client,
        from_operator=True,
    )
