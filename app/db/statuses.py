# What it does: Append-only status/event timeline per lead (e.g. "new", "replied", "estimate
#   drafted", "taken over by the owner"). Separate from the current-status field on the Lead record —
#   this is the history, not just the latest value.
# When it runs: Called any time a lead's status changes, alongside updating Lead.status.
# What calls it: app/webhooks.py, app/tools.py, wherever a lead's state changes.
from . import records

STATUSES_DIR = records.KINDS_ROOT / "statuses"


def record(lead_id: str, event: str, detail: str = "") -> None:
    line = f"{records.now_iso()} | {event}"
    if detail:
        line += f" | {detail}"
    records.append_line(STATUSES_DIR, lead_id, line)


def history(lead_id: str) -> list[str]:
    return records.read_lines(STATUSES_DIR, lead_id)
