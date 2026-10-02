# What it does: Messaging abstraction — one interface for sending/receiving lead messages,
#   implemented per platform (Thumbtack now, others later). Keeps the agent and the rest of the
#   app decoupled from any one platform's API (decided 2026-09-22).
# When it runs: Implemented by app/messaging/thumbtack.py; consumed by app/tools.py.
# What calls it: app/tools.py wraps a MessagingClient as agent tools.
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class Message:
    sender: str  # "lead" | "agent" (sent by the AI) | "operator" (the human pro replying by hand)
    text: str
    sent_at: str
    message_id: str | None = None


class MessagingClient(ABC):
    @abstractmethod
    async def send_message(self, session_id: str, text: str) -> None: ...

    @abstractmethod
    async def get_messages(self, session_id: str) -> list[Message]: ...
