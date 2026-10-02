# What it does: DynamoDB record store — same calls as app/db/records_files.py. One item per record in
#   the table from app/db/dynamo_table.py: pk = kind (the folder's name, e.g. "leads"), sk = record id,
#   the record's fields as top-level attributes. Line records (statuses, sent messages) keep their lines
#   in a "lines" list on the item. Floats are stored as Decimal (DynamoDB's number type) and come back
#   as int when whole, else float.
# When it runs: Whenever app/db/records.py picks the dynamodb backend (DB_BACKEND=dynamodb).
# What calls it: app/db/records.py.
from decimal import Decimal
from pathlib import Path
from typing import Any

from boto3.dynamodb.conditions import Key

from . import dynamo_table

KEY_ATTRS = ("pk", "sk")
LINES_ATTR = "lines"


def _kind(dir_path: Path) -> str:
    return dir_path.name


def _to_dynamo(value: Any) -> Any:
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {k: _to_dynamo(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_dynamo(v) for v in value]
    return value


def _from_dynamo(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {k: _from_dynamo(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_from_dynamo(v) for v in value]
    return value


def _item(dir_path: Path, record_id: str, fields: dict[str, Any]) -> dict[str, Any]:
    clash = [k for k in (*KEY_ATTRS, LINES_ATTR) if k in fields]
    if clash:
        raise ValueError(f"Record fields can't use reserved names: {clash}")
    return {"pk": _kind(dir_path), "sk": record_id, **_to_dynamo(fields)}


def save(dir_path: Path, record_id: str, fields: dict[str, Any], body: str = "") -> None:
    # body: markdown body of the file backend — no caller uses it, not stored.
    dynamo_table.table().put_item(Item=_item(dir_path, record_id, fields))


def load(dir_path: Path, record_id: str) -> dict[str, Any] | None:
    item = dynamo_table.table().get_item(Key={"pk": _kind(dir_path), "sk": record_id}).get("Item")
    if item is None:
        return None
    return {k: _from_dynamo(v) for k, v in item.items() if k not in KEY_ATTRS}


def exists(dir_path: Path, record_id: str) -> bool:
    key = {"pk": _kind(dir_path), "sk": record_id}
    return "Item" in dynamo_table.table().get_item(Key=key, ProjectionExpression="pk")


def delete(dir_path: Path, record_id: str) -> None:
    dynamo_table.table().delete_item(Key={"pk": _kind(dir_path), "sk": record_id})


def _query_kind(dir_path: Path, **extra) -> list[dict[str, Any]]:
    """Every item of the kind, sorted by id (DynamoDB returns them in sk order)."""
    query = {"KeyConditionExpression": Key("pk").eq(_kind(dir_path)), **extra}
    items: list[dict[str, Any]] = []
    while True:
        page = dynamo_table.table().query(**query)
        items.extend(page["Items"])
        if "LastEvaluatedKey" not in page:
            return items
        query["ExclusiveStartKey"] = page["LastEvaluatedKey"]


def list_ids(dir_path: Path) -> list[str]:
    return [item["sk"] for item in _query_kind(dir_path, ProjectionExpression="sk")]


def load_all(dir_path: Path) -> list[dict[str, Any]]:
    return [{k: _from_dynamo(v) for k, v in item.items() if k not in KEY_ATTRS} for item in _query_kind(dir_path)]


def replace_all(dir_path: Path, by_id: dict[str, dict[str, Any]]) -> None:
    """Makes the kind hold exactly these records (batch writes; used for seeding)."""
    kind = _kind(dir_path)
    stale = set(list_ids(dir_path)) - set(by_id)
    with dynamo_table.table().batch_writer() as batch:
        for record_id in stale:
            batch.delete_item(Key={"pk": kind, "sk": record_id})
        for record_id, fields in by_id.items():
            batch.put_item(Item=_item(dir_path, record_id, fields))


def append_line(dir_path: Path, record_id: str, line: str) -> None:
    dynamo_table.table().update_item(
        Key={"pk": _kind(dir_path), "sk": record_id},
        UpdateExpression="SET #lines = list_append(if_not_exists(#lines, :empty), :new)",
        ExpressionAttributeNames={"#lines": LINES_ATTR},
        ExpressionAttributeValues={":empty": [], ":new": [line]},
    )


def read_lines(dir_path: Path, record_id: str) -> list[str]:
    item = dynamo_table.table().get_item(Key={"pk": _kind(dir_path), "sk": record_id}).get("Item")
    return list(item.get(LINES_ATTR, [])) if item else []
