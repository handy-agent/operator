# What it does: Shared plumbing for the two-window simulator: per-conversation file paths, tailing
#   a JSON-lines file for new entries, the agent lock (so the chat and notes windows never run the
#   agent at the same time), and the notes-to-operator log.
# When it runs: Imported by both simulator windows.
# What calls it: sim/chat.py, sim/notes.py.
import asyncio
import fcntl
import json
import sys
import termios
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.note import AGENT, DIM, LEAD, YOU, Note  # noqa: F401 — colors re-exported for the sim windows

# Conversation files of each sim run (git-ignored), next to the sim code.
SIM_DIR = Path(__file__).resolve().parent / "runs"


@dataclass
class SimPaths:
    thread: Path
    notes: Path
    lock: Path


def paths(sim_id: str) -> SimPaths:
    base = SIM_DIR / sim_id
    base.mkdir(parents=True, exist_ok=True)
    return SimPaths(thread=base / "thread.jsonl", notes=base / "notes.jsonl", lock=base / "agent.lock")


def color(text: str, style: str) -> str:
    return f"\033[{style}m{text}\033[0m"


def write_note(path: Path, note: Note) -> None:
    entry = {"at": datetime.now(timezone.utc).isoformat(), "note": note.to_dict()}
    with path.open("a") as f:
        f.write(json.dumps(entry) + "\n")


@asynccontextmanager
async def agent_lock(path: Path):
    with path.open("w") as f:
        await asyncio.to_thread(fcntl.flock, f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def read_note(entry: dict) -> Note:
    return Note(**entry["note"])


async def tail(path: Path, on_entry: Callable[[dict], None], from_start: bool = True) -> None:
    """Calls on_entry for every JSON line appended to path, polling twice a second."""
    seen = 0 if from_start or not path.exists() else len(path.read_text().splitlines())
    while True:
        if path.exists():
            lines = [line for line in path.read_text().splitlines() if line.strip()]
            for line in lines[seen:]:
                on_entry(json.loads(line))
            seen = len(lines)
        await asyncio.sleep(0.5)


# True only while input() is actually waiting — so show() redraws the prompt only then. Redrawing
# it while the agent is running doubled it up ("Customer: Customer:") once input() printed its own.
_waiting_for_input = False


def show(text: str, prompt: str) -> None:
    """Prints text above the input line, redrawing the prompt only if input is waiting."""
    sys.stdout.write(f"\r\033[K{text}\n{prompt if _waiting_for_input else ''}")
    sys.stdout.flush()


async def read_line(prompt: str) -> str | None:
    global _waiting_for_input
    # Keys pressed while the agent ran (e.g. Enter) sit in the terminal buffer, unechoed because the
    # agent's subprocess switches the terminal mode. They'd be read as an empty line and the prompt
    # reprinted on the same line ("> > "). Drop them, and clear whatever is on the current line.
    if sys.stdin.isatty():
        termios.tcflush(sys.stdin, termios.TCIFLUSH)
        sys.stdout.write("\r\033[K")
    _waiting_for_input = True
    try:
        line = (await asyncio.to_thread(input, prompt)).strip()
        sys.stdout.write("\n")  # empty row after every message you type (decided 2026-09-24)
        return line
    except EOFError:
        return None
    finally:
        _waiting_for_input = False
