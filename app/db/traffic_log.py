# What it does: Saves every Thumbtack exchange as one record (kind thumbtack_traffic), both directions: each
#   webhook delivery Thumbtack sends us with our response, and each API call we make to Thumbtack with its
#   response. Kept as recorded real traffic for future testing (a new Thumbtack connection costs money).
#   Secrets (Authorization header) are redacted. Holds customer data.
# When it runs: On every POST /webhooks/thumbtack and every Thumbtack API call.
# What calls it: app/main.py, app/messaging/thumbtack.py.
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from . import records

TRAFFIC_DIR = records.KINDS_ROOT / "thumbtack_traffic"
REDACTED_HEADERS = {"authorization", "cookie", "set-cookie"}


def body_value(body: bytes | str | None) -> Any:
    """JSON bodies as parsed JSON, anything else as text."""
    if body is None or body in (b"", ""):
        return None
    text = body.decode("utf-8", errors="replace") if isinstance(body, bytes) else body
    try:
        return json.loads(text)
    except ValueError:
        return text


def redact(headers: dict[str, str]) -> dict[str, str]:
    return {k: ("<redacted>" if k.lower() in REDACTED_HEADERS else v) for k, v in headers.items()}


def save(direction: str, request: dict[str, Any], response: dict[str, Any] | None = None,
         error: str | None = None) -> str:
    """direction: "inbound" (Thumbtack -> us, a webhook) or "outbound" (us -> Thumbtack API).
    request/response: {"method", "url", "headers", "body"} / {"status", "headers", "body"}.
    Returns the record id: <UTC time>-<direction>-<random>, so ids sort by time."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    record_id = f"{stamp}-{direction}-{uuid.uuid4().hex[:6]}"
    entry = {
        "at": records.now_iso(),
        "direction": direction,
        "request": {**request, "headers": redact(request.get("headers") or {})},
        "response": response and {**response, "headers": redact(response.get("headers") or {})},
        "error": error,
    }
    records.save(TRAFFIC_DIR, record_id, entry)
    return record_id
