# What it does: Markdown-file record store. Each record is a file with YAML frontmatter (structured
#   fields) and an optional markdown body, under the given folder. The first "database" (decided
#   2026-09-22); now the fallback backend — unit tests use it (DB_BACKEND unset).
# When it runs: Whenever app/db/records.py picks the files backend (DB_BACKEND=files or unset).
# What calls it: app/db/records.py.
from pathlib import Path
from typing import Any

import yaml

FRONTMATTER_DELIM = "---\n"


def record_path(dir_path: Path, record_id: str) -> Path:
    return dir_path / f"{record_id}.md"


def save(dir_path: Path, record_id: str, fields: dict[str, Any], body: str = "") -> None:
    dir_path.mkdir(parents=True, exist_ok=True)
    frontmatter = yaml.safe_dump(fields, sort_keys=False)
    record_path(dir_path, record_id).write_text(f"{FRONTMATTER_DELIM}{frontmatter}{FRONTMATTER_DELIM}\n{body}")


def load(dir_path: Path, record_id: str) -> dict[str, Any] | None:
    path = record_path(dir_path, record_id)
    if not path.exists():
        return None
    text = path.read_text()
    _, frontmatter, _ = text.split(FRONTMATTER_DELIM, 2)
    return yaml.safe_load(frontmatter) or {}


def exists(dir_path: Path, record_id: str) -> bool:
    return record_path(dir_path, record_id).exists()


def delete(dir_path: Path, record_id: str) -> None:
    record_path(dir_path, record_id).unlink(missing_ok=True)


def list_ids(dir_path: Path) -> list[str]:
    if not dir_path.exists():
        return []
    return sorted(p.stem for p in dir_path.glob("*.md"))


def load_all(dir_path: Path) -> list[dict[str, Any]]:
    return [load(dir_path, record_id) for record_id in list_ids(dir_path)]


def replace_all(dir_path: Path, by_id: dict[str, dict[str, Any]]) -> None:
    for record_id in set(list_ids(dir_path)) - set(by_id):
        delete(dir_path, record_id)
    for record_id, fields in by_id.items():
        save(dir_path, record_id, fields)


def append_line(dir_path: Path, record_id: str, line: str) -> None:
    dir_path.mkdir(parents=True, exist_ok=True)
    with record_path(dir_path, record_id).open("a") as f:
        f.write(f"{line}\n")


def read_lines(dir_path: Path, record_id: str) -> list[str]:
    path = record_path(dir_path, record_id)
    if not path.exists():
        return []
    return [line.rstrip("\n") for line in path.read_text().splitlines() if line.strip()]
