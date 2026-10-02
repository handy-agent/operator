# What it does: Chat window of the two-window simulator — both sides of the Thumbtack thread.
#   Plain text or /in <text> = a message from the lead (runs the same webhook handler as production).
#   /out <text> = the operator replying by hand (pauses the agent on this lead until /resume).
#   Agent replies appear here; notes to the operator go to the notes window.
# When it runs: Opened by sh/sim.sh.
# What calls it: sh/sim.sh (python -m sim.chat <sim_id> [account_id]).
import asyncio
import os
import sys

from dotenv import load_dotenv

from app.db import held_replies, sessions
from app.note import system
from app.reply_timing import ReplyScheduler, delays_from_env
from app.webhooks import handle_thumbtack_event, make_estimator, make_item_lookup, run_batched_turn
from . import common as sim_common
from .file_thread import FileThreadMessagingClient

PROMPT = "> "


async def main(sim_id: str, account_id: str | None = None) -> None:
    load_dotenv()
    # Short so testing isn't slow; production holds 10 min for the operator (app/tools.py).
    os.environ.setdefault("OPERATOR_HOLD_SECONDS", "60")
    paths = sim_common.paths(sim_id)
    client = FileThreadMessagingClient(paths.thread)
    print(sim_common.color(
        f"Chat — lead {sim_id}\n"
        "  <text>        lead writes\n"
        "  /out <text>   you reply by hand (pauses the agent)\n"
        "  /quit         end\n", sim_common.DIM))

    def on_message(entry: dict) -> None:
        # Lead and operator lines were typed here, so only the agent's replies need printing.
        if entry["sender"] == "agent":
            sim_common.show(sim_common.color(f"Agent › {entry['text']}", sim_common.AGENT) + "\n", PROMPT)

    start_lookup = make_item_lookup(client, lambda note: sim_common.write_note(paths.notes, note))
    start_estimate = make_estimator(client, lambda note: sim_common.write_note(paths.notes, note))

    async def reply(negotiation_id: str, texts: list[str]) -> None:
        async with sim_common.agent_lock(paths.lock):
            note = await run_batched_turn(negotiation_id, texts, client, start_lookup, start_estimate)
        if note:
            sim_common.write_note(paths.notes, note)

    # Short delays so testing isn't slow; production waits 20-60s (see app/main.py).
    scheduler = ReplyScheduler(reply, **delays_from_env("SIM_REPLY", 2, 4, 15))

    tail_task = asyncio.create_task(sim_common.tail(paths.thread, on_message))
    try:
        while True:
            text = await sim_common.read_line(PROMPT)
            if text is None or text == "/quit":
                break
            if not text:
                continue
            if text.startswith("/out "):
                client.add_operator_message(text.removeprefix("/out ").strip())
                held_replies.clear(sim_id)
                if sessions.find(sim_id) is not None:
                    sessions.mark_taken_over(sim_id)
                continue
            text = text.removeprefix("/in ").strip()
            message = client.add_lead_message(text)
            result = await handle_thumbtack_event(
                {
                    "negotiationID": sim_id,
                    "messageID": f"{sim_id}:{message.message_id}",
                    "from": "Customer",
                    "text": text,
                    "sentAt": message.sent_at,
                    "customer": {"displayName": f"Sim {sim_id[-6:-2]}"},  # e.g. "Sim 0420": tells sim topics apart
                },
                messaging_client=client,
                scheduler=scheduler,
                account_id=account_id,
            )
            if result.get("taken_over"):
                sim_common.write_note(paths.notes, system("⏸ Paused (you replied by hand). /resume to hand back."))
            elif not result.get("handled") or result.get("stopped_status"):
                sim_common.write_note(paths.notes, system(f"Agent didn't run: {result.get('reason') or result}"))
    finally:
        tail_task.cancel()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None))
