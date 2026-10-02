# What it does: The contract every operator channel implements (Telegram now; SMS, app later), plus the
#   channel-neutral "who is talking to the lead now" status every channel shows.
#   Inbound (the customer typing to the agent) is each channel's own transport, but always ends in
#   app/operator_input.py after the channel checked the sender is linked to the lead's account
#   (app/db/channel_links.py).
# When it runs: Whenever a note goes to a customer or a channel shows a lead's status.
# What calls it: app/channels/notifier.py, app/telegram/channel.py.
from collections.abc import Awaitable, Callable
from typing import Literal, Protocol

from ..db import leads, sessions
from ..note import Note

# Runs the agent on the customer's instruction for a lead; returns the agent's note to them.
OnInstruction = Callable[[str, str], Awaitable[Note | None]]


class OperatorChannel(Protocol):
    async def notify(self, account_id: str, lead_id: str, note: Note) -> None:
        """Delivers a note about a lead to every address the account linked on this channel."""

    async def sync_all(self) -> None:
        """Brings every shown "who is talking" status up to date (it changes outside the channel too,
        e.g. the customer replying by hand on Thumbtack)."""


# What the operator sees about a lead at a glance, in this order (decided 2026-09-25: the pinned card
# shows the job, not just the status). (icon, text) pairs; each channel lays them out its own way.
_CARD_FIELDS = [("🛠", "service"), ("📍", "location"), ("📅", "preferred_day"), ("🔗", "item_link"), ("📷", "photos")]


def lead_card(lead_id: str) -> list[tuple[str, str]]:
    lead = leads.find(lead_id)
    if lead is None:
        return []
    return [(icon, getattr(lead, name)) for icon, name in _CARD_FIELDS if getattr(lead, name)]


def platform_link(lead_id: str) -> tuple[str, str] | None:
    """("Open in Thumbtack", url) when the lead's platform page is known."""
    lead = leads.find(lead_id)
    if lead is None or not lead.platform_url:
        return None
    return f"Open in {lead.platform.capitalize()}", lead.platform_url


def talker(lead_id: str) -> Literal["agent", "operator"]:
    session = sessions.find(lead_id)
    return "operator" if session and session.taken_over else "agent"
