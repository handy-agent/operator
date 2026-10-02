# What it does: Estimate records — one per estimate prepared for a lead. Tracks where the price
#   came from (existing pricing DB match vs. fresh research) and its approval state, since price
#   always needs the owner's yes before it's sent as a message (see ../../agent/reply-style.md).
# When it runs: Created when the operator has gathered enough detail to price a job.
# What calls it: app/tools.py (estimate-prep tool), future estimate/pricing logic.
import uuid
from dataclasses import asdict, dataclass, field

from . import records

ESTIMATES_DIR = records.KINDS_ROOT / "estimates"


@dataclass
class Estimate:
    estimate_id: str
    lead_id: str
    service: str
    price_text: str | None = None
    suggested: int | None = None
    confidence: int | None = None  # 1-10, see app/estimate.py
    approved_price: float | None = None  # what the owner actually quoted
    decided_at: str | None = None
    source: str = "pricing_db"  # "pricing_db" | "research"
    rough: bool = False  # made before the lead sent a link or photos — size not checked
    # "draft" | "superseded" (a newer estimate replaced it) | "approved" (as suggested) | "changed" (the owner set another price)
    status: str = "draft"
    created_at: str = field(default_factory=records.now_iso)
    updated_at: str = field(default_factory=records.now_iso)


def find(estimate_id: str) -> Estimate | None:
    data = records.load(ESTIMATES_DIR, estimate_id)
    return Estimate(**data) if data is not None else None


def save(estimate: Estimate) -> None:
    estimate.updated_at = records.now_iso()
    records.save(ESTIMATES_DIR, estimate.estimate_id, asdict(estimate))


def create(lead_id: str, service: str, **fields) -> Estimate:
    """New draft for the lead; any earlier draft becomes "superseded" (re-estimate after new details)."""
    for older in list_for_lead(lead_id):
        if older.status == "draft":
            older.status = "superseded"
            save(older)
    estimate_id = f"{lead_id}-{uuid.uuid4().hex[:8]}"
    estimate = Estimate(estimate_id=estimate_id, lead_id=lead_id, service=service, **fields)
    save(estimate)
    return estimate


def latest(lead_id: str) -> Estimate | None:
    """The lead's newest estimate, whatever its status (a decided one included)."""
    return max(list_for_lead(lead_id), key=lambda e: e.created_at, default=None)


def latest_draft(lead_id: str) -> Estimate | None:
    drafts = [e for e in list_for_lead(lead_id) if e.status == "draft"]
    return max(drafts, key=lambda e: e.created_at, default=None)


def record_decision(lead_id: str, price_sent: float) -> Estimate | None:
    """the owner's price went out: mark the latest draft approved (as suggested) or changed."""
    draft = latest_draft(lead_id)
    if draft is None:
        return None
    draft.approved_price = price_sent
    draft.status = "approved" if draft.suggested is not None and price_sent == draft.suggested else "changed"
    draft.decided_at = records.now_iso()
    save(draft)
    return draft


def list_for_lead(lead_id: str) -> list[Estimate]:
    return [
        e
        for eid in records.list_ids(ESTIMATES_DIR)
        if (e := find(eid)) is not None and e.lead_id == lead_id
    ]
