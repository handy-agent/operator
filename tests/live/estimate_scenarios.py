# What it does: Live end-to-end estimate scenarios against the real agent (costs Claude usage, ~1 min
#   each). Each scenario runs lead messages and operator instructions through the same code as the
#   simulator, then checks what the lead received and what was recorded on the estimate.
#   Not part of the unit suite (no "test_" prefix) because it calls the model.
# When it runs: By hand after changing prompts or estimate logic.
# What calls it: sh/live-estimate-scenarios.sh.
import asyncio
import os
import re
import shutil
import sys

from dotenv import load_dotenv

load_dotenv(".env")
os.environ["OPERATOR_HOLD_SECONDS"] = "3600"  # no "let me check" fallback during a scenario

from app import agent  # noqa: E402
from app.db import estimates, records  # noqa: E402
from sim import common  # noqa: E402
from sim.file_thread import FileThreadMessagingClient  # noqa: E402
from app import estimator  # noqa: E402
from app.webhooks import handle_thumbtack_event  # noqa: E402
from app.note import Note, render_text


def _text(note: Note | None) -> str:
    # Raw status wording, so checks like "waiting on roman" still match.
    return (render_text(note) + f"\n{note.status or ''}") if note else ""

LINK = "https://www.ikea.com/us/en/p/malm-6-drawer-dresser-white-30360468/"
OPENING = f"Hi, I need this IKEA dresser assembled: {LINK} Friday afternoon works. How much?"


class Scenario:
    def __init__(self, name: str) -> None:
        self.sid = f"sim-live-{name}"
        self.cleanup()
        self.client = FileThreadMessagingClient(common.paths(self.sid).thread)
        self.notes: list[str] = []

    async def lead(self, text: str) -> None:
        m = self.client.add_lead_message(text)
        r = await handle_thumbtack_event(
            {"negotiationID": self.sid, "messageID": m.message_id, "from": "Customer", "text": text},
            messaging_client=self.client,
        )
        self.notes.append(_text(r.get("note_to_operator")))
        # The app runs this in the background alongside the reply; here it's awaited so checks can see it.
        before = estimates.latest_draft(self.sid)
        await estimator.run(self.sid, self.client)
        if (after := estimates.latest_draft(self.sid)) and after is not before and (before is None or after.estimate_id != before.estimate_id):
            self.notes.append(_text(estimator.as_note(after)))

    async def operator(self, text: str) -> None:
        self.notes.append(_text(
            await agent.run_agent_turn(
                session_id=self.sid, lead_id=self.sid, incoming_text=text, messaging_client=self.client, from_operator=True
            )
        ))

    def agent_texts(self) -> list[str]:
        return [m.text for m in self.client.read_all() if m.sender == "agent"]

    def prices_sent(self) -> list[str]:
        return re.findall(r"\$(\d+)", " ".join(self.agent_texts()))

    def estimate(self):
        found = estimates.list_for_lead(self.sid)
        return max(found, key=lambda e: e.created_at) if found else None

    def cleanup(self) -> None:
        shutil.rmtree(common.SIM_DIR / self.sid, ignore_errors=True)
        for sub in ("leads", "sessions", "statuses", "processed_events", "held_replies", "estimates"):
            for record_id in records.list_ids(records.KINDS_ROOT / sub):
                if record_id.startswith(self.sid):
                    records.delete(records.KINDS_ROOT / sub, record_id)


def check(results: list, name: str, ok: bool, detail: str) -> None:
    results.append((name, ok, detail))


async def approve_as_suggested(results: list) -> None:
    s = Scenario("approve")
    await s.lead(OPENING)
    e = s.estimate()
    check(results, "approve: estimate drafted with confidence", bool(e and e.suggested and e.confidence), str(e and (e.suggested, e.confidence)))
    check(results, "approve: no price sent before approval", not s.prices_sent(), str(s.agent_texts()))
    await s.operator("approve")
    e = s.estimate()
    check(results, "approve: suggested price sent to lead", bool(e and str(e.suggested) in s.prices_sent()), str(s.agent_texts()[-1:]))
    check(results, "approve: estimate marked approved", bool(e and e.status == "approved"), str(e and (e.status, e.approved_price)))
    s.cleanup()


async def roman_changes_price(results: list) -> None:
    s = Scenario("changed")
    await s.lead(OPENING)
    await s.operator("make it 175")
    e = s.estimate()
    check(results, "changed: lead gets $175", "175" in s.prices_sent(), str(s.agent_texts()[-1:]))
    check(results, "changed: suggested price not sent", bool(e and str(e.suggested) not in s.prices_sent()), str(s.prices_sent()))
    check(results, "changed: estimate marked changed at 175", bool(e and e.status == "changed" and e.approved_price == 175), str(e and (e.status, e.approved_price)))
    s.cleanup()


async def roman_wants_photos_first(results: list) -> None:
    s = Scenario("photos")
    await s.lead(OPENING)
    await s.operator("before I price it, ask them for a photo of the box")
    last = s.agent_texts()[-1] if s.agent_texts() else ""
    check(results, "photos: asks lead for a photo", "photo" in last.lower(), last)
    check(results, "photos: no price sent", not s.prices_sent(), str(s.prices_sent()))
    s.cleanup()


async def lead_haggles(results: list) -> None:
    s = Scenario("haggle")
    await s.lead(OPENING)
    await s.operator("approve")
    sent_before = list(s.prices_sent())
    await s.lead("Hmm, can you do $90?")
    check(results, "haggle: agent doesn't accept $90 on its own", "90" not in s.prices_sent(), str(s.agent_texts()[-1:]))
    check(results, "haggle: no new price sent", s.prices_sent() == sent_before, str(s.prices_sent()))
    check(results, "haggle: the owner is asked", "roman" in s.notes[-1].lower() or "waiting on roman" in s.notes[-1].lower(), s.notes[-1][:200])
    s.cleanup()


async def main() -> None:
    results: list = []
    for scenario in (approve_as_suggested, roman_changes_price, roman_wants_photos_first, lead_haggles):
        await scenario(results)
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"\n        {detail[:300]}"))
    failed = sum(not ok for _, ok, _ in results)
    print(f"\n{len(results) - failed}/{len(results)} checks passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
