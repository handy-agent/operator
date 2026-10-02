# What it does: A reply held back while the agent waits for the operator's decision (price, time,
#   anything to confirm). If the operator answers in time, the hold is cleared and the agent replies
#   with his real answer; if not, the fallback text (e.g. "Let me check and get back to you on
#   that.") is sent when the hold expires. File-backed so the simulator's two processes share it.
# When it runs: Saved by the hold_for_operator tool; cleared on any operator instruction or manual
#   reply; checked when the hold timer fires.
# What calls it: app/tools.py, app/agent.py, app/webhooks.py, sim/chat.py.
import uuid

from . import records

HELD_DIR = records.KINDS_ROOT / "held_replies"


def hold(session_id: str, fallback_text: str) -> str:
    """Saves the held reply (replacing any older one) and returns its hold ID."""
    hold_id = uuid.uuid4().hex[:12]
    records.save(HELD_DIR, session_id, {"hold_id": hold_id, "fallback_text": fallback_text, "held_at": records.now_iso()})
    return hold_id


def take_if_current(session_id: str, hold_id: str) -> str | None:
    """Returns and clears the fallback text, only if this hold is still the current one."""
    data = records.load(HELD_DIR, session_id)
    if data is None or data.get("hold_id") != hold_id:
        return None
    clear(session_id)
    return data["fallback_text"]


def clear(session_id: str) -> None:
    records.delete(HELD_DIR, session_id)
