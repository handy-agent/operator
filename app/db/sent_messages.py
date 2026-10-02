# What it does: Log of texts the agent itself sent, per session. Thumbtack marks every pro-side
#   message the same way, so this is how we tell the agent's replies apart from the operator's
#   own manual replies (which pause the agent — see app/webhooks.py).
# When it runs: Written on every agent send; read whenever the thread is fetched.
# What calls it: app/messaging/thumbtack.py.
import json

from . import records

SENT_DIR = records.KINDS_ROOT / "sent_messages"


def record(session_id: str, text: str) -> None:
    records.append_line(SENT_DIR, session_id, json.dumps(text))


def texts(session_id: str) -> set[str]:
    return {json.loads(line) for line in records.read_lines(SENT_DIR, session_id)}
