# What it does: Local stand-in for a platform MessagingClient — keeps the thread in memory and
#   prints the agent's replies to the terminal instead of sending them anywhere.
# When it runs: Only during local simulation (sh/chat.sh). Never used for real leads.
# What calls it: sim/single.py.
from datetime import datetime, timezone

from app.messaging.base import Message, MessagingClient


class ConsoleMessagingClient(MessagingClient):
    def __init__(self) -> None:
        self.messages: list[Message] = []

    def add_lead_message(self, text: str) -> Message:
        message = Message(sender="lead", text=text, sent_at=_now(), message_id=f"sim-{len(self.messages) + 1}")
        self.messages.append(message)
        return message

    def add_operator_message(self, text: str) -> Message:
        # The operator replying by hand in the thread (like typing in the Thumbtack app) — not the agent.
        message = Message(sender="operator", text=text, sent_at=_now(), message_id=f"sim-{len(self.messages) + 1}")
        self.messages.append(message)
        return message

    async def send_message(self, session_id: str, text: str) -> None:
        self.messages.append(Message(sender="agent", text=text, sent_at=_now(), message_id=f"sim-{len(self.messages) + 1}"))
        print(f"\n\033[1;32mAgent › {text}\033[0m\n")

    async def get_messages(self, session_id: str) -> list[Message]:
        return list(self.messages)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
