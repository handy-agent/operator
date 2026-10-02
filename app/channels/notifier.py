# What it does: Sends every note to the lead's account on all its channels (Telegram now; SMS, app later),
#   one channel failing never stops the others, and keeps each channel's status display in sync.
# When it runs: For the life of the Operator app.
# What calls it: app/main.py.
import asyncio
import logging

from ..db import leads
from ..note import Note
from .base import OperatorChannel

STATUS_SYNC_SECONDS = 10
log = logging.getLogger("operator")


class Notifier:
    def __init__(self, channels: list[OperatorChannel]) -> None:
        self.channels = channels
        self._tasks: set[asyncio.Task] = set()

    async def notify(self, lead_id: str, note: Note) -> None:
        lead = leads.find(lead_id)
        if lead is None or lead.account_id is None:
            log.warning("Note for %s not delivered: lead has no account", lead_id)
            return
        for channel in self.channels:
            try:
                await channel.notify(lead.account_id, lead_id, note)
            except Exception:
                log.exception("Note for %s failed on %s", lead_id, type(channel).__name__)

    def notify_soon(self, lead_id: str, note: Note) -> None:
        """notify() from sync code (e.g. the item-lookup callback)."""
        task = asyncio.get_running_loop().create_task(self.notify(lead_id, note))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def run_status_sync(self) -> None:
        while True:
            for channel in self.channels:
                try:
                    await channel.sync_all()
                except Exception:
                    log.exception("Status sync failed on %s", type(channel).__name__)
            await asyncio.sleep(STATUS_SYNC_SECONDS)
