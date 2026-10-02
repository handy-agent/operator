# What it does: The record store every app/db module uses. Picks the backend from DB_BACKEND:
#   "dynamodb" -> app/db/records_dynamo.py (DynamoDB: local in Docker, or AWS);
#   "files" or unset -> app/db/records_files.py (markdown files under the given folder; unit tests).
#   Callers name a record by (folder, id); with DynamoDB the folder's name is the record kind.
# When it runs: On every record read/write.
# What calls it: app/db/*.py (leads, sessions, estimates, accounts, channel links...), app/telegram/channel.py.
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import records_dynamo, records_files

# Root of the record kinds: callers name a kind as KINDS_ROOT / "<kind>". DynamoDB uses only the kind
# name. The file backend (unit tests, which point each kind at a temp folder) writes under the folder.
KINDS_ROOT = Path(tempfile.gettempdir()) / "operator-records"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def backend():
    name = os.environ.get("DB_BACKEND", "files")
    if name == "dynamodb":
        return records_dynamo
    if name == "files":
        return records_files
    raise ValueError(f"DB_BACKEND must be 'dynamodb' or 'files', got {name!r}")


def save(dir_path: Path, record_id: str, fields: dict[str, Any], body: str = "") -> None:
    backend().save(dir_path, record_id, fields, body)


def load(dir_path: Path, record_id: str) -> dict[str, Any] | None:
    return backend().load(dir_path, record_id)


def exists(dir_path: Path, record_id: str) -> bool:
    return backend().exists(dir_path, record_id)


def delete(dir_path: Path, record_id: str) -> None:
    backend().delete(dir_path, record_id)


def list_ids(dir_path: Path) -> list[str]:
    return backend().list_ids(dir_path)


def load_all(dir_path: Path) -> list[dict[str, Any]]:
    """Every record of the folder/kind, sorted by id."""
    return backend().load_all(dir_path)


def replace_all(dir_path: Path, by_id: dict[str, dict[str, Any]]) -> None:
    """Makes the folder/kind hold exactly these records (seeding)."""
    backend().replace_all(dir_path, by_id)


def append_line(dir_path: Path, record_id: str, line: str) -> None:
    backend().append_line(dir_path, record_id, line)


def read_lines(dir_path: Path, record_id: str) -> list[str]:
    return backend().read_lines(dir_path, record_id)
