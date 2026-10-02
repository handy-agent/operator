# What it does: Notes window of the two-window simulator — the starting point for the real
#   notification system. Shows every note to the operator as it happens and takes the operator's
#   instructions to the agent (trusted; a price in one is approved) and /resume.
# When it runs: Opened by sh/sim.sh.
# What calls it: sh/sim.sh (python -m sim.notes <sim_id>).
import asyncio
import sys

from dotenv import load_dotenv

from app import operator_input
from app.note import render_terminal, system
from app.db import sessions
from . import common as sim_common
from .file_thread import FileThreadMessagingClient

PROMPT = "> "


async def main(sim_id: str) -> None:
    load_dotenv()
    paths = sim_common.paths(sim_id)
    client = FileThreadMessagingClient(paths.thread)
    print(sim_common.color(
        f"Notes — lead {sim_id}\n"
        "  <text>    instruction to the agent (\"approve $110, Fri 3pm\")\n"
        "  /pause    you take over (or \"stop\")\n"
        "  /resume   agent takes back (or \"continue\")\n"
        "  /quit     end\n", sim_common.DIM))

    def on_note(entry: dict) -> None:
        sim_common.show(render_terminal(sim_common.read_note(entry)) + "\n" + sim_common.color("─" * 40, sim_common.DIM), PROMPT)

    tail_task = asyncio.create_task(sim_common.tail(paths.notes, on_note))
    try:
        while True:
            text = await sim_common.read_line(PROMPT)
            if text is None or text == "/quit":
                break
            if not text:
                continue
            if reply := operator_input.control_command(sim_id, text):
                sim_common.show(render_terminal(system(reply)), PROMPT)
                continue
            if sessions.find(sim_id) is None:
                sim_common.show(render_terminal(system(operator_input.NO_LEAD)), PROMPT)
                continue
            sim_common.show(sim_common.color("… agent working", sim_common.DIM), PROMPT)
            async with sim_common.agent_lock(paths.lock):
                note = await operator_input.run_instruction(sim_id, text, client)
            if note:
                sim_common.write_note(paths.notes, note)
    finally:
        tail_task.cancel()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
