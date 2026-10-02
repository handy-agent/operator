# What it does: Account records — one per customer (a handyman like the owner) using Operator. Each holds its
#   own settings (see app/settings.py). Leads belong to an
#   account, and a customer's channels (Telegram now; SMS, app later) only ever see that account's leads.
# When it runs: Created when a customer is onboarded (sh/connect-telegram.sh emulates that for now).
# What calls it: app/connect.py, app/webhooks.py.
import os
from dataclasses import asdict, dataclass, field

from . import records

ACCOUNTS_DIR = records.KINDS_ROOT / "accounts"


@dataclass
class Account:
    account_id: str
    name: str
    settings: dict = field(default_factory=dict)  # only what differs from app/settings.py DEFAULTS
    created_at: str = field(default_factory=records.now_iso)


def find(account_id: str) -> Account | None:
    data = records.load(ACCOUNTS_DIR, account_id)
    return Account(**data) if data is not None else None


def save(account: Account) -> None:
    records.save(ACCOUNTS_DIR, account.account_id, asdict(account))


def find_or_create(account_id: str, name: str) -> Account:
    account = find(account_id)
    if account is None:
        account = Account(account_id=account_id, name=name)
        save(account)
    return account


def for_platform_event(payload: dict) -> str | None:
    """Which account a platform webhook event belongs to. One connected Thumbtack business for now
    (OPERATOR_ACCOUNT_ID); mapping each business's events to its account comes with per-business
    Thumbtack connections."""
    return os.getenv("OPERATOR_ACCOUNT_ID")
