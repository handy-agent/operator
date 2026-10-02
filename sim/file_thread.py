# What it does: Simulator MessagingClient backed by one JSON-lines file per conversation, so two
#   processes (the chat window and the operator's notes window) share the same thread. Nothing is
#   sent to Thumbtack.
# When it runs: Only in the two-window simulator (sh/sim.sh).
# What calls it: sim/chat.py, sim/notes.py.
import json
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from app.messaging.base import Message, MessagingClient


class FileThreadMessagingClient(MessagingClient):
    def __init__(self, path: Path) -> None:
        self.path = path

    def add_lead_message(self, text: str) -> Message:
        return self._append("lead", text)

    def add_operator_message(self, text: str) -> Message:
        # The operator replying by hand (like typing in the Thumbtack app) — not the agent.
        return self._append("operator", text)

    async def send_message(self, session_id: str, text: str) -> None:
        self._append("agent", text)

    async def get_messages(self, session_id: str) -> list[Message]:
        return self.read_all()

    def read_all(self) -> list[Message]:
        if not self.path.exists():
            return []
        return [Message(**json.loads(line)) for line in self.path.read_text().splitlines() if line.strip()]

    def _append(self, sender: str, text: str) -> Message:
        message = Message(
            sender=sender,
            text=text,
            sent_at=datetime.now(timezone.utc).isoformat(),
            message_id=uuid.uuid4().hex[:12],
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as f:
            f.write(json.dumps(asdict(message)) + "\n")
        return message
