# What it does: Telegram in place of the simulator's Notes window — test the phone channel end to end
#   without Thumbtack. The sim lead belongs to the given account; every note about it goes to that
#   account's Telegram chats (one topic for the lead, also printed here), and what the customer types in
#   that topic (or the Pause/Resume buttons) drives the sim lead's agent. /start connect links work too.
# When it runs: Opened by sh/sim.sh --telegram <account_id>. Needs TELEGRAM_BOT_TOKEN in .env and
#   Operator stopped (Telegram serves updates to one reader at a time).
# What calls it: sh/sim.sh (python -m sim.telegram <sim_id>).
import asyncio
import sys

from dotenv import load_dotenv

from app import operator_input
from app.channels.notifier import Notifier
from app.note import Note, render_terminal, system
from app.telegram.channel import TelegramChannel
from . import common as sim_common
from .file_thread import FileThreadMessagingClient


async def main(sim_id: str) -> None:
    load_dotenv()
    paths = sim_common.paths(sim_id)
    client = FileThreadMessagingClient(paths.thread)

    async def run_instruction(lead_id: str, text: str) -> Note | None:
        if lead_id != sim_id:
            # An older sim run's topic: its thread isn't this run's, so never act on it here.
            return system("Old sim topic — this run only handles its own lead.")
        print(sim_common.color(f"      You › {text}", sim_common.YOU), flush=True)
        async with sim_common.agent_lock(paths.lock):
            return await operator_input.run_instruction(lead_id, text, client)

    telegram = TelegramChannel.from_env(run_instruction)
    if telegram is None:
        print("Telegram isn't set up: TELEGRAM_BOT_TOKEN missing in .env (see sh/README.md).")
        return
    notifier = Notifier([telegram])
    print(sim_common.color(f"Telegram — lead {sim_id}. Notes go to the account's chats; answer there.\n", sim_common.DIM), flush=True)

    # tail() calls back synchronously; a queue keeps notes in order on the way to Telegram.
    notes: asyncio.Queue[dict] = asyncio.Queue()

    async def send_notes() -> None:
        while True:
            note = sim_common.read_note(await notes.get())
            print(render_terminal(note) + "\n" + sim_common.color("─" * 40, sim_common.DIM), flush=True)
            await notifier.notify(sim_id, note)

    await asyncio.gather(
        sim_common.tail(paths.notes, notes.put_nowait), send_notes(), telegram.listen(), notifier.run_status_sync()
    )


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
