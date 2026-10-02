# What it does: Reads the pricing catalog from the record store (DynamoDB): subservices (with their
#   service_id) and order-level multipliers. Seeded from db/seed/ by app/db/seed.py.
# When it runs: Whenever an estimate is calculated or the agent needs the list of subservices.
# What calls it: app/estimate.py, app/tools.py, app/prices_api.py.
from .db import records

SERVICES_DIR = records.KINDS_ROOT / "services"
SUBSERVICES_DIR = records.KINDS_ROOT / "subservices"
MULTIPLIERS_DIR = records.KINDS_ROOT / "multipliers"


def subservices() -> list[dict]:
    return records.load_all(SUBSERVICES_DIR)


def subservice(subservice_id: str) -> dict | None:
    return records.load(SUBSERVICES_DIR, subservice_id)


def multipliers() -> list[dict]:
    return records.load_all(MULTIPLIERS_DIR)
