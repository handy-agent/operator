# What it does: Seeds the record store (DynamoDB, or files in tests) from the seed files in db/seed/ —
#   the pricing catalog: services.json (services: sk META; subservices: sk SUB#<id>) and multipliers.json.
#   Each kind ends up holding exactly what the seed files have (removed items are deleted), so it's safe
#   to rerun. The table/endpoint come from the environment, so the same seeding runs locally and per stage.
# When it runs: On a fresh local table (sh/dynamo-local.sh), by hand (sh/dynamo-seed.sh), and when an AWS
#   stage's init (operator-deploy) finds its table empty.
# What calls it: sh/dynamo-seed.sh (python -m app.db.seed); tests.
import json
from pathlib import Path
from typing import Any

from .. import catalog
from . import records

# app/db/seed.py -> parents[2] is operator/.
SEED_DIR = Path(__file__).resolve().parents[2] / "db" / "seed"


def _fields(item: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in item.items() if k not in ("pk", "sk")}


def catalog_records(seed_dir: Path) -> dict[Path, dict[str, dict[str, Any]]]:
    """Seed files -> {kind folder: {id: fields}}."""
    services: dict[str, dict[str, Any]] = {}
    subservices: dict[str, dict[str, Any]] = {}
    for item in json.loads((seed_dir / "services.json").read_text()):
        service_id = item["pk"].removeprefix("SERVICE#")
        if item["sk"] == "META":
            services[service_id] = {"id": service_id, **_fields(item)}
        else:
            sub_id = item["sk"].removeprefix("SUB#")
            subservices[sub_id] = {"id": sub_id, "service_id": service_id, **_fields(item)}
    multipliers = {
        (mult_id := item["pk"].removeprefix("MULT#")): {"id": mult_id, **_fields(item)}
        for item in json.loads((seed_dir / "multipliers.json").read_text())
    }
    return {catalog.SERVICES_DIR: services, catalog.SUBSERVICES_DIR: subservices, catalog.MULTIPLIERS_DIR: multipliers}


def seed(seed_dir: Path = SEED_DIR) -> dict[str, int]:
    counts = {}
    for kind_dir, by_id in catalog_records(seed_dir).items():
        records.replace_all(kind_dir, by_id)
        counts[kind_dir.name] = len(by_id)
    return counts


if __name__ == "__main__":
    import os

    from dotenv import load_dotenv

    load_dotenv()
    print(f"Seeding {os.environ.get('DB_BACKEND', 'files')} "
          f"table={os.environ.get('DYNAMODB_TABLE', 'operator')} "
          f"endpoint={os.environ.get('DYNAMODB_ENDPOINT_URL') or 'AWS'}")
    for kind, count in seed().items():
        print(f"{kind:<14} {count}")
