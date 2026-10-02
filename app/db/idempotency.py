# What it does: Tracks which inbound webhook/message IDs have already been processed, so a
#   Thumbtack retry doesn't trigger a duplicate agent run or duplicate outbound message.
# When it runs: Checked at the top of every webhook event, before any agent/DB work happens.
# What calls it: app/webhooks.py.
from . import records

PROCESSED_DIR = records.KINDS_ROOT / "processed_events"


def already_handled(event_id: str) -> bool:
    return records.exists(PROCESSED_DIR, event_id)


def mark_handled(event_id: str) -> None:
    records.save(PROCESSED_DIR, event_id, {"event_id": event_id, "handled_at": records.now_iso()})
