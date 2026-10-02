# What it does: Telegram as an operator channel (decided 2026-09-25). One bot for the whole product:
#   - connect: the customer opens t.me/<bot>?start=<code> (app/connect.py makes the link); /start <code>
#     links their Telegram user and private chat to their account (app/db/channel_links.py);
#   - in that private chat, one topic per lead: every note about the lead is posted there (Telegram
#     pushes it to the phone). One button for the current status — Pause while the agent talks, Resume
#     while paused — sits in two places (decided 2026-09-25): a status card pinned at the top of the topic
#     (edited in place, no new message) and the latest note. Optional; typing works too;
#   - the topic title shows who is talking to the lead now: 🤖 the agent, 👤 the customer;
#   - whatever the customer types in a lead's topic goes to the agent as their instruction;
#   - alarm (decided 2026-09-25): a note that waits on the customer pings them in the lead's topic every
#     alarm_every_seconds for alarm_for_seconds (their settings), until they tap "I'm here", send /here or
#     write anything.
#     All pings are deleted once it stops. (Deleting each previous ping as the next one came cut the
#     phone's buzzing, the owner 2026-09-25 — so they pile up while it rings.)
#   Only linked users, and only for their own account's leads — their instructions are trusted.
# When it runs: For the life of the Operator app (app/main.py) or a Telegram simulator run (sim/telegram.py).
# What calls it: app/main.py, sim/telegram.py.
import asyncio
import logging
import os
from collections import defaultdict
from collections.abc import Awaitable

from .. import operator_input, settings
from ..channels.base import OnInstruction, lead_card, platform_link, talker
from ..db import accounts, channel_links, leads, records
from ..note import Note, render_html, render_text
from .api import TelegramApi, TelegramError

CHANNEL = "telegram"
TOPICS_DIR = records.KINDS_ROOT / "telegram_topics"
MAX_TEXT = 4000  # Telegram's limit is 4096 characters per message
MAX_NAME = 20  # topic titles stay short (decided 2026-09-25): status icon + customer name only
ICONS = {"agent": "🤖", "operator": "👤"}

NOT_CONNECTED = "Not connected. Open your connect link."
BAD_CODE = "Link invalid or expired. Ask for a new one."
WRITE_IN_TOPIC = "Write in a lead's topic."

log = logging.getLogger("operator")


def status_title(lead_id: str) -> str:
    lead = leads.find(lead_id)
    name = ((lead.name if lead else None) or lead_id)[:MAX_NAME]
    return f"{ICONS[talker(lead_id)]} {name}"


def chunks(text: str) -> list[str]:
    return [text[i : i + MAX_TEXT] for i in range(0, len(text), MAX_TEXT)] or [""]


def button_action(lead_id: str) -> str:
    """The one button a topic shows: Pause while the agent is talking, Resume once paused."""
    return "pause" if talker(lead_id) == "agent" else "resume"


def buttons(lead_id: str, action: str) -> list[list[dict]]:
    return [[{"text": action.capitalize(), "callback_data": f"{action}:{lead_id}"}]]


def card_text(lead_id: str) -> str:
    """The pinned card: who is talking, then the job as known so far."""
    status = f"{ICONS['agent']} Agent is talking" if talker(lead_id) == "agent" else f"{ICONS['operator']} You're talking · agent paused"
    return "\n".join([status, *(f"{icon} {text}" for icon, text in lead_card(lead_id))])


def card_buttons(lead_id: str, action: str) -> list[list[dict]]:
    """The note button, plus "Open in Thumbtack" (or the lead's platform) when its page is known."""
    rows = buttons(lead_id, action)
    if link := platform_link(lead_id):
        rows.append([{"text": link[0], "url": link[1]}])
    return rows


def connected_text(account_name: str) -> str:
    return (
        f"✅ Connected: {account_name}\n"
        "One topic per lead. Type there to instruct the agent (\"approve $110, Fri 3pm\"), or /pause, /resume."
    )


def _link_list(lead_id: str) -> list[str] | None:
    link = platform_link(lead_id)
    return list(link) if link else None  # records store lists, not tuples


def _topic_gone(error: TelegramError) -> bool:
    return any(s in str(error) for s in ("TOPIC_ID_INVALID", "thread not found", "TOPIC_DELETED"))


def _topic_id(chat_id: int, lead_id: str) -> str:
    return f"{chat_id}_{lead_id}"


class TelegramChannel:
    def __init__(self, api: TelegramApi, on_instruction: OnInstruction) -> None:
        self.api = api
        self.on_instruction = on_instruction
        self._tasks: set[asyncio.Task] = set()
        # One update at a time per topic: a button tap, a new note and the status sync used to edit the
        # same message at once, and the loser failed (a note was lost).
        self._topic_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._alarms: dict[int, asyncio.Task] = {}  # chat_id -> the running alarm (one per chat)

    @classmethod
    def from_env(cls, on_instruction: OnInstruction) -> "TelegramChannel | None":
        """None when the product bot isn't configured (no TELEGRAM_BOT_TOKEN)."""
        if not os.getenv("TELEGRAM_BOT_TOKEN"):
            return None
        return cls(TelegramApi(), on_instruction)

    # --- outbound -------------------------------------------------------------------------------

    async def notify(self, account_id: str, lead_id: str, note: Note) -> None:
        for link in channel_links.for_account(account_id, CHANNEL):
            chat_id = link.address["chat_id"]
            try:
                await self._post(chat_id, lead_id, note)
            except TelegramError as error:
                if not _topic_gone(error):
                    raise
                # The customer deleted the lead's topic: forget it and post into a new one.
                records.delete(TOPICS_DIR, _topic_id(chat_id, lead_id))
                await self._post(chat_id, lead_id, note)
            if note.needs:
                self._start_alarm(chat_id, lead_id, note.needs, settings.for_account(account_id))

    # --- alarm ----------------------------------------------------------------------------------

    def _start_alarm(self, chat_id: int, lead_id: str, needs: str, values: dict) -> None:
        self.stop_alarm(chat_id)  # the newest thing waiting on them replaces an older alarm
        every, total = float(values["alarm_every_seconds"]), float(values["alarm_for_seconds"])
        task = asyncio.get_running_loop().create_task(self._alarm(chat_id, lead_id, needs, every, total))
        self._alarms[chat_id] = task
        task.add_done_callback(lambda t: self._alarms.pop(chat_id, None) if self._alarms.get(chat_id) is t else None)

    def stop_alarm(self, chat_id: int) -> None:
        if task := self._alarms.pop(chat_id, None):
            task.cancel()

    async def _alarm(self, chat_id: int, lead_id: str, needs: str, every: float, total: float) -> None:
        thread_id = await self._topic(chat_id, lead_id)
        button = [[{"text": "I'm here", "callback_data": f"here:{lead_id}"}]]
        pings: list[int] = []
        loop = asyncio.get_running_loop()
        ends = loop.time() + total
        try:
            while loop.time() < ends:
                sent = await self.api.send_message(chat_id, f"⏰ Waiting on you: {needs}", thread_id, button)
                pings.append(sent["message_id"])
                await asyncio.sleep(every)
        finally:
            # deleteMessages takes up to 100 IDs per call (5 min every 5 s = 60).
            for i in range(0, len(pings), 100):
                try:
                    await self.api.delete_messages(chat_id, pings[i : i + 100])
                except TelegramError:
                    log.warning("Couldn't delete alarm pings in %s", chat_id, exc_info=True)

    async def _post(self, chat_id: int, lead_id: str, note: Note) -> None:
        async with self._topic_locks[_topic_id(chat_id, lead_id)]:
            await self._post_locked(chat_id, lead_id, note)

    async def _post_locked(self, chat_id: int, lead_id: str, note: Note) -> None:
        thread_id = await self._topic(chat_id, lead_id)
        await self._sync_topic_locked(_topic_id(chat_id, lead_id))
        lead = leads.find(lead_id)
        formatted = render_html(note, (lead.name if lead else None) or "Lead")
        # HTML can't be cut at any character without breaking tags; a note that long goes as plain text.
        parts = [formatted] if len(formatted) <= MAX_TEXT else chunks(render_text(note))
        is_html = len(parts) == 1 and parts[0] is formatted
        for part in parts[:-1]:
            await self.api.send_message(chat_id, part, thread_id)
        action = button_action(lead_id)
        sent = await self.api.send_message(chat_id, parts[-1], thread_id, buttons(lead_id, action), html=is_html)
        await self._move_button(_topic_id(chat_id, lead_id), sent["message_id"], action)

    async def sync_all(self) -> None:
        for topic_id in records.list_ids(TOPICS_DIR):
            try:
                await self._sync_topic(topic_id)
            except TelegramError as error:
                if _topic_gone(error):  # deleted by the customer: stop tracking it; a new note makes a new one
                    records.delete(TOPICS_DIR, topic_id)
                else:  # one broken topic mustn't stop the rest
                    log.warning("Couldn't sync Telegram topic %s", topic_id, exc_info=True)

    # --- inbound: polling (local, simulator) or webhook (production) ----------------------------

    async def listen(self) -> None:
        """Long-polls Telegram for updates. Local and simulator runs; production uses the webhook."""
        await self.api.delete_webhook()  # getUpdates doesn't work while a webhook is set
        offset = None
        while True:
            try:
                for update in await self.api.get_updates(offset):
                    offset = update["update_id"] + 1
                    self.handle_soon(update)
            except Exception:
                log.exception("Telegram poll failed; retrying")
                await asyncio.sleep(5)

    def handle_soon(self, update: dict) -> None:
        """Handles an update in the background — an agent turn can take minutes."""
        self._spawn(self.handle_update(update))

    async def handle_update(self, update: dict) -> None:
        if query := update.get("callback_query"):
            await self._handle_button(query)
        elif message := update.get("message"):
            await self._handle_message(message)

    async def _handle_button(self, query: dict) -> None:
        action, _, lead_id = query.get("data", "").partition(":")
        link = channel_links.find(CHANNEL, str(query["from"]["id"]))
        if not self._owns(link, lead_id):
            await self.api.answer_button(query["id"], NOT_CONNECTED)
            return
        self.stop_alarm(link.address["chat_id"])  # any tap means they're here
        if action == "here":
            await self.api.answer_button(query["id"], "👍")
            return
        reply = operator_input.control_command(lead_id, f"/{action}")
        await self.api.answer_button(query["id"], reply or "Unknown button")
        await self._sync_topic(_topic_id(link.address["chat_id"], lead_id))

    async def _handle_message(self, message: dict) -> None:
        chat = message["chat"]
        if chat.get("type") != "private":
            return
        chat_id, sender = chat["id"], str(message["from"]["id"])
        thread_id = message.get("message_thread_id")
        text = (message.get("text") or "").strip()
        if text == "/start" or text.startswith("/start "):
            await self._connect(chat_id, sender, text.removeprefix("/start").strip())
            return
        link = channel_links.find(CHANNEL, sender)
        if link is None:
            await self.api.send_message(chat_id, NOT_CONNECTED)
            return
        self.stop_alarm(chat_id)  # anything they send means they're here
        lead_id = self._lead_for_thread(chat_id, thread_id)
        if not text or text == "/here":
            return
        if lead_id is None or not self._owns(link, lead_id):
            await self.api.send_message(chat_id, WRITE_IN_TOPIC, thread_id)
            return
        if reply := operator_input.control_command(lead_id, text):
            await self.api.send_message(chat_id, reply, thread_id)
            await self._sync_topic(_topic_id(chat_id, lead_id))
            return
        try:
            await self.api.react(chat_id, message["message_id"], "👀")  # "got it, working on it"
        except TelegramError:
            log.warning("Telegram reaction failed", exc_info=True)
        note = await self.on_instruction(lead_id, text)
        if note:
            await self.notify(link.account_id, lead_id, note)
        else:
            await self._sync_topic(_topic_id(chat_id, lead_id))

    async def _connect(self, chat_id: int, sender: str, code: str) -> None:
        account_id = channel_links.redeem(code, CHANNEL) if code else None
        if account_id is None:
            already = channel_links.find(CHANNEL, sender)
            await self.api.send_message(chat_id, "Already connected." if already else BAD_CODE)
            return
        channel_links.link(CHANNEL, sender, account_id, {"chat_id": chat_id})
        account = accounts.find(account_id)
        await self.api.send_message(chat_id, connected_text(account.name if account else account_id))

    # --- topics ---------------------------------------------------------------------------------

    async def _topic(self, chat_id: int, lead_id: str) -> int:
        topic_id = _topic_id(chat_id, lead_id)
        topic = records.load(TOPICS_DIR, topic_id)
        if topic is not None:
            return topic["thread_id"]
        title, action, text = status_title(lead_id), button_action(lead_id), card_text(lead_id)
        thread_id = await self.api.create_topic(chat_id, title)
        card = await self.api.send_message(chat_id, text, thread_id, card_buttons(lead_id, action), silent=True)
        records.save(TOPICS_DIR, topic_id, {
            "chat_id": chat_id, "lead_id": lead_id, "thread_id": thread_id, "title": title,
            "card_message_id": card["message_id"], "card_text": text, "card_link": _link_list(lead_id),
            "button_action": action,
        })
        try:
            await self.api.pin(chat_id, card["message_id"])
        except TelegramError:  # the card still works unpinned, as the topic's first message
            log.warning("Couldn't pin the status card in %s", topic_id, exc_info=True)
        return thread_id

    async def _sync_topic(self, topic_id: str) -> None:
        async with self._topic_locks[topic_id]:
            await self._sync_topic_locked(topic_id)

    async def _sync_topic_locked(self, topic_id: str) -> None:
        """Brings the topic title, pinned card and button in line with the lead now (who is talking,
        what's known about the job). Only what changed is edited; edits don't buzz the phone."""
        topic = records.load(TOPICS_DIR, topic_id)
        if topic is None:
            return
        lead_id, chat_id = topic["lead_id"], topic["chat_id"]
        title, action, text = status_title(lead_id), button_action(lead_id), card_text(lead_id)
        link = _link_list(lead_id)
        card_changed = text != topic.get("card_text") or link != topic.get("card_link") or action != topic.get("button_action")
        if title == topic["title"] and not card_changed:
            return
        if title != topic["title"]:
            await self.api.rename_topic(chat_id, topic["thread_id"], title)
        if card_changed and (card_id := topic.get("card_message_id")):
            await self.api.edit_message(chat_id, card_id, text, card_buttons(lead_id, action))
        if action != topic.get("button_action") and (note_id := topic.get("button_message_id")):
            await self.api.set_buttons(chat_id, note_id, buttons(lead_id, action))
        records.save(TOPICS_DIR, topic_id, {**topic, "title": title, "card_text": text, "card_link": link, "button_action": action})

    async def _move_button(self, topic_id: str, message_id: int, action: str) -> None:
        """The newest note gets the button; the previous one loses it — one button per topic."""
        topic = records.load(TOPICS_DIR, topic_id)
        if previous := topic.get("button_message_id"):
            try:
                await self.api.set_buttons(topic["chat_id"], previous, None)
            except TelegramError:
                log.warning("Couldn't remove the old button in %s", topic_id, exc_info=True)
        records.save(TOPICS_DIR, topic_id, {**topic, "button_message_id": message_id, "button_action": action})

    def _lead_for_thread(self, chat_id: int, thread_id: int | None) -> str | None:
        if thread_id is None:
            return None
        for topic_id in records.list_ids(TOPICS_DIR):
            topic = records.load(TOPICS_DIR, topic_id)
            if topic["chat_id"] == chat_id and topic["thread_id"] == thread_id:
                return topic["lead_id"]
        return None

    @staticmethod
    def _owns(link: channel_links.ChannelLink | None, lead_id: str) -> bool:
        lead = leads.find(lead_id) if lead_id else None
        return link is not None and lead is not None and lead.account_id == link.account_id

    def _spawn(self, coro: Awaitable[None]) -> None:
        task = asyncio.get_running_loop().create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._done)

    def _done(self, task: asyncio.Task) -> None:
        self._tasks.discard(task)
        if not task.cancelled() and task.exception():
            log.error("Telegram task failed", exc_info=task.exception())
