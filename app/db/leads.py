# What it does: Lead records — one per Thumbtack negotiation. `lead_id` is the Thumbtack
#   negotiation ID, so a lead always maps 1:1 to a Thumbtack thread.
# When it runs: Created on the first webhook event for a new negotiation ID; read/updated
#   throughout the lead's lifecycle (details gathering, estimate, hand-off).
# What calls it: app/webhooks.py (find-or-create on incoming events), app/tools.py (agent reads).
from dataclasses import asdict, dataclass, field

from . import records

LEADS_DIR = records.KINDS_ROOT / "leads"


@dataclass
class Lead:
    lead_id: str
    platform: str = "thumbtack"
    platform_url: str | None = None  # the lead's page on its platform, for the operator's "Open in …" link
    account_id: str | None = None  # the customer (the handyman using Operator) this lead belongs to
    name: str | None = None
    phone: str | None = None
    service: str | None = None
    location: str | None = None
    item_link: str | None = None
    photos: str | None = None  # what the lead sent (count/description/URLs) — needed before estimating
    item_lookup_started: bool = False  # background product search already run for this lead (once only)
    preferred_day: str | None = None
    state: str | None = None  # e.g. "TX", for the location multiplier
    lead_cost: float | None = None  # what the platform charged for this lead (not agent-writable)
    status: str = "new"
    created_at: str = field(default_factory=records.now_iso)
    updated_at: str = field(default_factory=records.now_iso)


# Records saved before the terminology change (2026-09-25) used "customer_*" for the lead's own details.
_OLD_FIELDS = {"customer_name": "name", "customer_phone": "phone"}


def find(lead_id: str) -> Lead | None:
    data = records.load(LEADS_DIR, lead_id)
    if data is None:
        return None
    for old, new in _OLD_FIELDS.items():
        if old in data:
            data[new] = data.pop(old)
    return Lead(**data)


def save(lead: Lead) -> None:
    lead.updated_at = records.now_iso()
    records.save(LEADS_DIR, lead.lead_id, asdict(lead))


def create(lead_id: str, **fields) -> Lead:
    lead = Lead(lead_id=lead_id, **fields)
    save(lead)
    return lead


def find_or_create(lead_id: str, **fields) -> tuple[Lead, bool]:
    """Returns (lead, is_new)."""
    existing = find(lead_id)
    if existing is not None:
        return existing, False
    return create(lead_id, **fields), True
