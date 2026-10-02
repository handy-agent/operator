# What it does: A note to the operator as data, and how every channel shows it (decided 2026-09-25:
#   fast to read — the lead's message and what we replied come first, system info after, few words).
#   What the lead wrote and what was sent are filled in by code from the thread, never retold by the
#   agent; the agent adds only the short status lines (see "Note to the owner" in app/system_prompt.py).
#   render_html for Telegram (reads like the Thumbtack chat: messages first, in quotes under who wrote
#   them; the action bold; system info in plain italics), render_text for plain phone channels (SMS later),
#   render_terminal for the simulators.
# When it runs: Every time a note goes to the operator.
# What calls it: app/agent.py, app/item_lookup.py, app/webhooks.py, app/main.py, app/channels/, app/telegram/,
#   sim/.
import html
from dataclasses import asdict, dataclass, field

# The agent's note lines -> Note fields. Anything else it writes lands in `lines`, so nothing is lost.
AGENT_FIELDS = {
    "status": "status", "waiting on owner for": "needs", "needs owner": "needs",
    "price suggestion": "price", "saved": "saved", "comment": "comment",
}
NONE_VALUES = {"", "none", "n/a", "-"}


@dataclass
class Note:
    source: str  # "lead" (lead wrote), "instruction" (operator's own), "lookup", "system"
    lead: list[str] = field(default_factory=list)  # the lead's messages this turn, word for word
    sent: list[str] = field(default_factory=list)  # what went to the lead this turn, word for word
    needs: str | None = None
    price: str | None = None
    status: str | None = None
    saved: str | None = None
    comment: str | None = None
    lines: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def from_agent(source: str, agent_text: str | None, lead: list[str], sent: list[str]) -> Note:
    note = Note(source=source, lead=list(lead), sent=list(sent))
    for raw in (agent_text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        key, sep, value = line.partition(":")
        name = AGENT_FIELDS.get(key.strip().lower()) if sep else None
        if key.strip().lower() == "sent" and sep:
            continue  # code already has the exact sent text
        if name is None:
            note.lines.append(line)
        elif value.strip().lower() not in NONE_VALUES:
            setattr(note, name, value.strip())
    return note


def system(text: str) -> Note:
    return Note(source="system", lines=[text])


def short_status(status: str) -> str:
    s = status.lower()
    if "customer" in s or "lead" in s:
        return "⏳ waiting on lead"
    if "owner" in s and "wait" in s:
        return "✋ waiting on you"
    if "hand" in s:
        return "👤 handed to you"
    if "nothing" in s:
        return "✓ nothing to do"
    return status


# Terminal colors (ANSI), shared with the simulators (sim/common.py).
LEAD, AGENT, YOU, NEEDS, PRICE, DIM = "1;36", "1;32", "1;34", "1;33", "35", "2"


# (icon, terminal label, ANSI style, text) in reading order: conversation first, then what the owner must
# do, then system info.
def _rows(note: Note) -> list[tuple[str, str, str, str]]:
    rows = [("💬", "Lead", LEAD, text) for text in note.lead]
    rows += [("➡️", "Sent", AGENT, text) for text in note.sent]
    if note.lead and not note.sent:
        rows.append(("➡️", "Sent", DIM, "nothing"))
    if note.needs:  # a state, not an order (decided 2026-09-25): "✋ waiting on you: day & time"
        rows.append(("✋", "Needs you", NEEDS, f"waiting on you: {note.needs}"))
    if note.price:
        rows.append(("💲", "Price", PRICE, note.price))
    if note.status and not note.needs:
        rows.append(("·", "Status", DIM, short_status(note.status)))
    if note.saved:
        rows.append(("💾", "Saved", DIM, note.saved))
    if note.comment:
        rows.append(("📝", "Note", DIM, note.comment))
    icon = "🔎" if note.source == "lookup" else "ℹ️"
    rows += [(icon, "Info", DIM, line) for line in note.lines]
    return rows


def render_text(note: Note) -> str:
    return "\n".join(f"{icon} {text}" for icon, _, _, text in _rows(note))


def render_terminal(note: Note) -> str:
    return "\n".join(f"\033[{style}m{label:>9} │ {text}\033[0m" for _, label, style, text in _rows(note))


def render_html(note: Note, lead_name: str = "Lead") -> str:
    """Telegram HTML. Telegram has no text colors, so quotes and bold do the work (decided 2026-09-25)."""
    e = html.escape
    parts = [f"<b>{e(lead_name)}</b>\n<blockquote>{e(text)}</blockquote>" for text in note.lead]
    parts += [f"<b>You</b> · <i>agent</i>\n<blockquote>{e(text)}</blockquote>" for text in note.sent]
    if note.lead and not note.sent:
        parts.append("<i>No reply sent</i>")
    if note.needs:
        parts.append(f"<b>✋ Waiting on you: {e(note.needs)}</b>")
    if note.price:
        parts.append(f"<b>💲 {e(note.price)}</b>")
    if note.source == "lookup":
        parts.append("<b>Item lookup</b>\n" + "\n".join(e(line) for line in note.lines))
    info = [short_status(note.status)] if note.status and not note.needs else []
    info += [f"saved: {note.saved}"] if note.saved else []
    info += [note.comment] if note.comment else []
    info += note.lines if note.source != "lookup" else []
    if info:
        # Plain italic, not a quote: quotes are for messages only (decided 2026-09-25).
        parts.append("<i>" + e("\n".join(info)) + "</i>")
    return "\n\n".join(parts)
