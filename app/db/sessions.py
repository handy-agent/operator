# What it does: Session records — one per Thumbtack negotiation, `session_id` == the Thumbtack
#   negotiation ID (same value as the matching lead's `lead_id`). Tracks whether the owner has taken
#   over messaging a lead manually (operator stops auto-replying), and the hybrid warm/cold Agent
#   SDK session state (decided 2026-09-23): while a lead is actively responding, the
#   SDK session is resumed (`sdk_session_id`); after the customer's session_warm_minutes of inactivity
#   (app/settings.py), the
#   next event rebuilds a fresh SDK session instead of resuming the stale one.
# When it runs: find_or_create is called on every incoming webhook event, before any reply logic
#   runs, to decide "new lead" vs. "continuing an existing thread" (the owner's rule, 2026-09-22).
# What calls it: app/webhooks.py, app/agent.py.
from dataclasses import asdict, dataclass, field
from datetime import datetime

from . import records

SESSIONS_DIR = records.KINDS_ROOT / "sessions"



@dataclass
class Session:
    session_id: str
    lead_id: str
    taken_over: bool = False
    sdk_session_id: str | None = None
    last_activity_at: str = field(default_factory=records.now_iso)
    created_at: str = field(default_factory=records.now_iso)
    updated_at: str = field(default_factory=records.now_iso)


def is_warm(session: Session, timeout_seconds: int) -> bool:
    if session.sdk_session_id is None:
        return False
    last_activity = datetime.fromisoformat(session.last_activity_at)
    elapsed = (datetime.now(last_activity.tzinfo) - last_activity).total_seconds()
    return elapsed < timeout_seconds


def mark_activity(session_id: str, sdk_session_id: str) -> Session:
    session = find(session_id)
    if session is None:
        raise ValueError(f"No session {session_id}")
    session.sdk_session_id = sdk_session_id
    session.last_activity_at = records.now_iso()
    save(session)
    return session


def find(session_id: str) -> Session | None:
    data = records.load(SESSIONS_DIR, session_id)
    return Session(**data) if data is not None else None


def save(session: Session) -> None:
    session.updated_at = records.now_iso()
    records.save(SESSIONS_DIR, session.session_id, asdict(session))


def create(session_id: str, lead_id: str) -> Session:
    session = Session(session_id=session_id, lead_id=lead_id)
    save(session)
    return session


def find_or_create(session_id: str, lead_id: str) -> tuple[Session, bool]:
    """Returns (session, is_new). is_new tells the caller whether to also create a lead."""
    existing = find(session_id)
    if existing is not None:
        return existing, False
    return create(session_id, lead_id), True


def mark_taken_over(session_id: str) -> Session:
    session = find(session_id)
    if session is None:
        raise ValueError(f"No session {session_id} to take over")
    session.taken_over = True
    save(session)
    return session


def resume(session_id: str) -> Session:
    """Hands a taken-over lead back to the agent (the owner's explicit command)."""
    session = find(session_id)
    if session is None:
        raise ValueError(f"No session {session_id} to resume")
    session.taken_over = False
    save(session)
    return session
