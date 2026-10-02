# What it does: Which channel addresses belong to which account, channel-neutral: a Telegram user now;
#   a phone number (SMS) or an app device later. Also one-time connect codes — the customer opens a
#   connect link carrying the code, and the channel links their address to the account.
# When it runs: On connect (code created, then redeemed) and on every message from a customer's channel
#   (who is this sender, which account).
# What calls it: app/connect.py, app/telegram/channel.py.
import secrets
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone

from . import records

LINKS_DIR = records.KINDS_ROOT / "channel_links"
CODES_DIR = records.KINDS_ROOT / "connect_codes"
CODE_TTL = timedelta(hours=24)


@dataclass
class ChannelLink:
    channel: str  # "telegram" (later "sms", "app")
    sender: str  # the channel's own sender ID: Telegram user ID, later a phone number / device ID
    account_id: str
    address: dict  # what the channel needs to reach them, e.g. {"chat_id": ...}
    linked_at: str = field(default_factory=records.now_iso)


def _link_id(channel: str, sender: str) -> str:
    return f"{channel}-{sender}"


def new_connect_code(account_id: str, channel: str) -> str:
    code = secrets.token_urlsafe(12)  # Telegram start parameters allow A-Z a-z 0-9 _ -
    expires = datetime.now(timezone.utc) + CODE_TTL
    records.save(CODES_DIR, code, {"account_id": account_id, "channel": channel, "expires_at": expires.isoformat()})
    return code


def redeem(code: str, channel: str) -> str | None:
    """Returns the code's account ID and burns the code; None if unknown, expired, or another channel's."""
    data = records.load(CODES_DIR, code) if code.replace("-", "").replace("_", "").isalnum() else None
    if data is None or data["channel"] != channel:
        return None
    records.delete(CODES_DIR, code)
    if datetime.fromisoformat(data["expires_at"]) < datetime.now(timezone.utc):
        return None
    return data["account_id"]


def link(channel: str, sender: str, account_id: str, address: dict) -> ChannelLink:
    link_ = ChannelLink(channel=channel, sender=sender, account_id=account_id, address=address)
    records.save(LINKS_DIR, _link_id(channel, sender), asdict(link_))
    return link_


def find(channel: str, sender: str) -> ChannelLink | None:
    data = records.load(LINKS_DIR, _link_id(channel, sender))
    return ChannelLink(**data) if data is not None else None


def for_account(account_id: str, channel: str) -> list[ChannelLink]:
    found = (records.load(LINKS_DIR, link_id) for link_id in records.list_ids(LINKS_DIR))
    return [ChannelLink(**d) for d in found if d["account_id"] == account_id and d["channel"] == channel]
