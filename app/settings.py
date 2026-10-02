# What it does: Per-customer settings (decided 2026-09-25): everything the owner decided about timing and
#   alerting is a default here, and each customer (handyman account) can differ and be changed while
#   the system runs — no code change, no deploy. An account stores only what differs from DEFAULTS.
# When it runs: Whenever a setting is needed for a lead (via its account) or an account.
# What calls it: app/main.py, app/webhooks.py, app/tools.py, app/agent.py, app/telegram/channel.py,
#   app/settings_cli.py.
from .db import accounts, leads

DEFAULTS: dict[str, float | bool] = {
    # Human-like reply timing (REQUIREMENTS.md "Human-like reply timing").
    "reply_delay_min_seconds": 20,
    "reply_delay_max_seconds": 60,
    "reply_max_wait_seconds": 120,
    "first_reply_immediate": True,  # a new lead's first message is answered right away
    # How long a reply needing the customer's decision waits for them before the fallback goes out.
    "operator_hold_seconds": 600,
    # Telegram alarm while a note waits on the customer.
    "alarm_every_seconds": 5,
    "alarm_for_seconds": 300,
    # How long an agent session stays warm after the last activity.
    "session_warm_minutes": 30,  # placeholder — the owner hasn't picked a value yet
}


def for_account(account_id: str | None) -> dict:
    account = accounts.find(account_id) if account_id else None
    return {**DEFAULTS, **(account.settings if account else {})}


def for_lead(lead_id: str) -> dict:
    lead = leads.find(lead_id)
    return for_account(lead.account_id if lead else None)


def parse(key: str, raw: str) -> float | bool:
    """Checks a setting name and turns its text value into the default's type."""
    if key not in DEFAULTS:
        raise ValueError(f"unknown setting '{key}'. Known: {', '.join(DEFAULTS)}")
    if isinstance(DEFAULTS[key], bool):
        if raw.lower() not in ("true", "false", "yes", "no", "on", "off", "1", "0"):
            raise ValueError(f"{key} is on/off, got '{raw}'")
        return raw.lower() in ("true", "yes", "on", "1")
    value = float(raw)
    if value < 0:
        raise ValueError(f"{key} can't be negative")
    return value


def update(account_id: str, changes: dict[str, str]) -> dict:
    """Saves the changes on the account ("default" removes an override). Returns the account's settings."""
    account = accounts.find(account_id)
    if account is None:
        raise ValueError(f"no account '{account_id}'")
    for key, raw in changes.items():
        if raw == "default":
            parse(key, str(DEFAULTS[key]))  # validates the name
            account.settings.pop(key, None)
        else:
            account.settings[key] = parse(key, raw)
    accounts.save(account)
    return for_account(account_id)
