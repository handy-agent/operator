# What it does: Unit tests for the Telegram operator channel as a multi-customer product: connecting a
#   customer with a one-time link, one topic per lead in their private chat, who-is-talking status in the
#   topic title, Pause/Resume, instructions to the agent, and customers never reaching each other's leads.
#   Telegram itself is faked; nothing goes over the network.
# When it runs: `.venv/bin/python -m unittest discover tests` from operator/.
# What calls it: developer / Claude, by hand.
import asyncio
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock

from app import settings
from app.channels.notifier import Notifier
from app.db import accounts, channel_links, leads, sessions
from app.note import Note
from app.telegram import channel as channel_module
from app.telegram.channel import BAD_CODE, NOT_CONNECTED, WRITE_IN_TOPIC, TelegramChannel, chunks

ROMAN, ROMAN_CHAT = 7, 70  # Telegram user ID and private chat ID
OTHER, OTHER_CHAT = 8, 80  # another customer (pro)


def _labels(buttons):
    return [b["text"] for row in buttons or [] for b in row]


class FakeApi:
    def __init__(self):
        self.sent, self.created, self.renames, self.reactions, self.button_answers = [], [], [], [], []
        self.buttons = {}  # message_id -> current button labels
        self.pinned, self.deleted = [], []
        self.next_thread = 500

    async def send_message(self, chat_id, text, thread_id=None, buttons=None, silent=False, html=False):
        message_id = len(self.sent) + 1
        self.sent.append({"chat_id": chat_id, "text": text, "thread_id": thread_id, "message_id": message_id,
                          "silent": silent, "html": html})
        self.buttons[message_id] = _labels(buttons)
        return {"message_id": message_id}

    async def edit_message(self, chat_id, message_id, text, buttons):
        self.sent[message_id - 1]["text"] = text
        self.buttons[message_id] = _labels(buttons)

    async def pin(self, chat_id, message_id):
        self.pinned.append(message_id)

    async def delete_messages(self, chat_id, message_ids):
        self.deleted += message_ids

    async def set_buttons(self, chat_id, message_id, buttons):
        self.buttons[message_id] = _labels(buttons)

    def with_buttons(self):
        return {message_id: labels for message_id, labels in self.buttons.items() if labels}

    async def create_topic(self, chat_id, name):
        self.next_thread += 1
        self.created.append((chat_id, name))
        return self.next_thread

    async def rename_topic(self, chat_id, thread_id, name):
        self.renames.append((thread_id, name))

    async def react(self, chat_id, message_id, emoji):
        self.reactions.append(message_id)

    async def answer_button(self, callback_query_id, text):
        self.button_answers.append(text)


class TelegramChannelTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        for module, attr in [(leads, "LEADS_DIR"), (sessions, "SESSIONS_DIR"), (accounts, "ACCOUNTS_DIR"),
                             (channel_links, "LINKS_DIR"), (channel_links, "CODES_DIR"),
                             (channel_module, "TOPICS_DIR")]:
            patcher = mock.patch.object(module, attr, root / attr)
            patcher.start()
            self.addCleanup(patcher.stop)
        accounts.find_or_create("atx", "ATX Handy Pros")
        accounts.find_or_create("other", "Other Pro")
        leads.create("neg-1", name="Ann", service="dresser assembly", account_id="atx")
        sessions.create("neg-1", lead_id="neg-1")
        leads.create("neg-2", name="Bob", account_id="other")
        sessions.create("neg-2", lead_id="neg-2")
        self.api = FakeApi()
        self.instructions = []

        async def on_instruction(lead_id, text):
            self.instructions.append((lead_id, text))
            return Note(source="instruction", sent=["$110, Friday 3pm works"], status="waiting on customer")

        self.channel = TelegramChannel(self.api, on_instruction)
        self.notifier = Notifier([self.channel])

    def run_(self, coro):
        return asyncio.run(coro)

    def message(self, text, sender=ROMAN, chat=ROMAN_CHAT, thread_id=None, chat_type="private"):
        update = {"message": {"message_id": 9, "chat": {"id": chat, "type": chat_type}, "from": {"id": sender},
                              "message_thread_id": thread_id, "text": text}}
        self.run_(self.channel.handle_update(update))

    def button(self, data, sender=ROMAN):
        self.run_(self.channel.handle_update({"callback_query": {"id": "q1", "from": {"id": sender}, "data": data}}))

    def connect(self, account_id="atx", sender=ROMAN, chat=ROMAN_CHAT):
        self.message(f"/start {channel_links.new_connect_code(account_id, 'telegram')}", sender=sender, chat=chat)

    def note(self, lead_id="neg-1", text="Needs a price.", needs=None):
        self.run_(self.notifier.notify(lead_id, Note(source="lead", lead=[text], needs=needs)))

    # --- connecting a customer ------------------------------------------------------------------

    def test_connect_link_ties_the_chat_to_the_account(self):
        self.connect()

        link = channel_links.find("telegram", str(ROMAN))
        self.assertEqual((link.account_id, link.address), ("atx", {"chat_id": ROMAN_CHAT}))
        self.assertIn("Connected: ATX Handy Pros", self.api.sent[-1]["text"])

    def test_connect_code_works_once(self):
        code = channel_links.new_connect_code("atx", "telegram")
        self.message(f"/start {code}")
        self.message(f"/start {code}", sender=OTHER, chat=OTHER_CHAT)

        self.assertIsNone(channel_links.find("telegram", str(OTHER)))
        self.assertEqual(self.api.sent[-1]["text"], BAD_CODE)

    def test_expired_or_unknown_code_does_not_connect(self):
        with mock.patch.object(channel_links, "CODE_TTL", timedelta(seconds=-1)):
            code = channel_links.new_connect_code("atx", "telegram")
        self.message(f"/start {code}")
        self.message("/start made-up-code")
        self.message("/start ../../accounts/atx")

        self.assertIsNone(channel_links.find("telegram", str(ROMAN)))

    def test_unconnected_user_gets_nothing_run(self):
        self.message("approve $10")

        self.assertEqual(self.api.sent[-1]["text"], NOT_CONNECTED)
        self.assertEqual(self.instructions, [])

    # --- notes, status, commands ----------------------------------------------------------------

    def test_note_goes_to_the_leads_topic_in_the_accounts_chat_only(self):
        self.connect()
        self.connect("other", sender=OTHER, chat=OTHER_CHAT)

        self.note()
        self.note(text="Photos came in.")

        self.assertEqual(self.api.created, [(ROMAN_CHAT, "🤖 Ann")])
        in_topic = [m for m in self.api.sent if m["thread_id"]]
        self.assertEqual([(m["chat_id"], m["thread_id"]) for m in in_topic], [(ROMAN_CHAT, 501)] * 3)
        self.assertEqual(in_topic[1]["text"],
                         "<b>Ann</b>\n<blockquote>Needs a price.</blockquote>\n\n<i>No reply sent</i>")
        self.assertTrue(in_topic[1]["html"])

    def test_topic_opens_with_a_silent_pinned_status_card(self):
        self.connect()

        self.note()

        card = next(m for m in self.api.sent if m["thread_id"])
        self.assertEqual(card["text"], "🤖 Agent is talking\n🛠 dresser assembly")
        self.assertTrue(card["silent"])
        self.assertEqual(self.api.pinned, [card["message_id"]])

    def test_pause_button_on_the_card_and_the_latest_note_only(self):
        self.connect()

        self.note()
        card, first = self.api.sent[-2]["message_id"], self.api.sent[-1]["message_id"]
        self.assertEqual(self.api.with_buttons(), {card: ["Pause"], first: ["Pause"]})

        self.note(text="Photos came in.")
        self.assertEqual(self.api.with_buttons(), {card: ["Pause"], self.api.sent[-1]["message_id"]: ["Pause"]})

    def test_every_linked_phone_of_the_account_gets_the_note(self):
        self.connect()
        self.connect(sender=99, chat=990)

        self.note()

        self.assertEqual(sorted(chat for chat, _ in self.api.created), [ROMAN_CHAT, 990])

    def test_title_shows_customer_when_they_took_over_renamed_only_on_change(self):
        self.connect()
        self.note()
        sessions.mark_taken_over("neg-1")  # e.g. replied by hand on Thumbtack

        self.run_(self.channel.sync_all())
        self.run_(self.channel.sync_all())

        self.assertEqual(self.api.renames, [(501, "👤 Ann")])

    def test_button_flips_between_pause_and_resume(self):
        self.connect()
        self.note()
        card, note_id = self.api.sent[-2]["message_id"], self.api.sent[-1]["message_id"]

        self.button("pause:neg-1")
        self.assertTrue(sessions.find("neg-1").taken_over)
        self.assertEqual(self.api.renames[-1], (501, "👤 Ann"))
        self.assertEqual(self.api.with_buttons(), {card: ["Resume"], note_id: ["Resume"]})
        self.assertEqual(self.api.sent[card - 1]["text"], "👤 You're talking · agent paused\n🛠 dresser assembly")

        self.button("resume:neg-1")
        self.assertFalse(sessions.find("neg-1").taken_over)
        self.assertEqual(self.api.renames[-1], (501, "🤖 Ann"))
        self.assertEqual(self.api.with_buttons(), {card: ["Pause"], note_id: ["Pause"]})

    def test_button_follows_status_changed_elsewhere(self):
        self.connect()
        self.note()
        sessions.mark_taken_over("neg-1")  # replied by hand on Thumbtack

        self.run_(self.channel.sync_all())

        self.assertEqual(list(self.api.with_buttons().values()), [["Resume"], ["Resume"]])

    def test_pause_typed_in_topic(self):
        self.connect()
        self.note()

        self.message("/pause", thread_id=501)

        self.assertTrue(sessions.find("neg-1").taken_over)
        self.assertEqual(self.instructions, [])

    def test_text_in_topic_is_an_instruction_and_the_agents_note_comes_back(self):
        self.connect()
        self.note()

        self.message("approve $110, Friday 3pm", thread_id=501)

        self.assertEqual(self.instructions, [("neg-1", "approve $110, Friday 3pm")])
        self.assertEqual(self.api.reactions, [9])
        self.assertEqual(self.api.sent[-1]["text"], "<b>You</b> · <i>agent</i>\n<blockquote>$110, Friday 3pm works</blockquote>"
                         "\n\n<i>⏳ waiting on lead</i>")

    def test_message_outside_a_lead_topic_is_not_run(self):
        self.connect()

        self.message("approve $110")

        self.assertEqual(self.instructions, [])
        self.assertEqual(self.api.sent[-1]["text"], WRITE_IN_TOPIC)

    # --- customers stay separate ----------------------------------------------------------------

    def test_customer_cannot_control_another_accounts_lead(self):
        self.connect()
        self.connect("other", sender=OTHER, chat=OTHER_CHAT)
        self.note()

        self.button("pause:neg-1", sender=OTHER)
        self.message("approve $10", sender=OTHER, chat=OTHER_CHAT, thread_id=501)  # the owner's thread ID

        self.assertFalse(sessions.find("neg-1").taken_over)
        self.assertEqual(self.instructions, [])

    def test_group_chats_are_ignored(self):
        self.connect()
        self.note()

        self.message("approve $110", chat=-100, thread_id=501, chat_type="supergroup")

        self.assertEqual(self.instructions, [])

    def test_lead_without_account_is_not_delivered(self):
        self.connect()
        leads.create("neg-3", name="Cat")

        self.note("neg-3")

        self.assertEqual(self.api.created, [])

    def test_topic_deleted_by_customer_is_forgotten_and_recreated(self):
        from app.telegram.api import TelegramError
        self.connect()
        self.note()
        sessions.mark_taken_over("neg-1")

        async def gone(*args):
            raise TelegramError("editForumTopic: Bad Request: TOPIC_ID_INVALID")

        with mock.patch.object(self.api, "rename_topic", gone):
            self.run_(self.channel.sync_all())  # no error escapes
        self.assertEqual(channel_module.records.list_ids(channel_module.TOPICS_DIR), [])

        self.note()
        self.assertEqual(len(self.api.created), 2)

    def test_button_tap_and_new_note_at_once_both_go_through(self):
        self.connect()
        self.note()
        busy = []

        async def slow_edit(chat_id, message_id, text, buttons):
            if busy:
                raise AssertionError("two updates of one topic at once")
            busy.append(1)
            await asyncio.sleep(0.01)
            busy.pop()

        async def both():
            tap = {"callback_query": {"id": "q1", "from": {"id": ROMAN}, "data": "pause:neg-1"}}
            await asyncio.gather(self.channel.handle_update(tap),
                                 self.notifier.notify("neg-1", Note(source="lead", lead=["hello?"])))

        sent_before = len(self.api.sent)
        with mock.patch.object(self.api, "edit_message", slow_edit):
            self.run_(both())
        self.assertEqual(len(self.api.sent), sent_before + 1)  # the note was delivered

    def test_card_shows_the_job_and_updates_silently_as_details_come_in(self):
        self.connect()
        self.note()
        card = next(m for m in self.api.sent if m["thread_id"])
        sent_before = len(self.api.sent)

        lead = leads.find("neg-1")
        lead.location, lead.preferred_day = "78641", "Friday"
        leads.save(lead)
        self.run_(self.channel.sync_all())

        self.assertEqual(self.api.sent[card["message_id"] - 1]["text"],
                         "🤖 Agent is talking\n🛠 dresser assembly\n📍 78641\n📅 Friday")
        self.assertEqual(len(self.api.sent), sent_before)  # edited in place, nothing new sent

    def test_card_links_to_the_lead_on_its_platform(self):
        lead = leads.find("neg-1")
        lead.platform_url = "https://www.thumbtack.com/pro-inbox/neg-1"
        leads.save(lead)
        self.connect()
        captured = {}
        original = self.api.send_message

        async def capture(chat_id, text, thread_id=None, buttons=None, silent=False, html=False):
            if silent:
                captured["buttons"] = buttons
            return await original(chat_id, text, thread_id, buttons, silent, html)

        with mock.patch.object(self.api, "send_message", capture):
            self.note()

        self.assertIn([{"text": "Open in Thumbtack", "url": "https://www.thumbtack.com/pro-inbox/neg-1"}],
                      captured["buttons"])

    # --- alarm ----------------------------------------------------------------------------------

    def alarm_run(self, stop):
        """Posts a note waiting on the owner, lets the alarm ping a few times, then calls stop()."""
        settings.update("atx", {"alarm_every_seconds": "0.01", "alarm_for_seconds": "5"})  # the customer's own
        async def scenario():
            await self.notifier.notify("neg-1", Note(source="lead", lead=["when?"], needs="day & time"))
            await asyncio.sleep(0.035)
            await stop()
            await asyncio.sleep(0.02)
        self.run_(scenario())
        return [m for m in self.api.sent if m["text"].startswith("⏰")]

    def test_alarm_pings_until_im_here_then_cleans_up(self):
        self.connect()
        tap = {"callback_query": {"id": "q1", "from": {"id": ROMAN}, "data": "here:neg-1"}}

        pings = self.alarm_run(lambda: self.channel.handle_update(tap))

        self.assertGreaterEqual(len(pings), 3)
        self.assertEqual(pings[0]["text"], "⏰ Waiting on you: day & time")
        self.assertEqual(self.api.buttons[pings[0]["message_id"]], ["I'm here"])
        self.assertEqual(self.api.deleted, [p["message_id"] for p in pings])  # all, once stopped
        self.assertEqual(self.channel._alarms, {})

    def test_pings_stay_while_ringing(self):
        self.connect()
        live = []

        async def check_then_stop():
            pings = [m["message_id"] for m in self.api.sent if m["text"].startswith("⏰")]
            live.extend(set(pings) - set(self.api.deleted))
            self.channel.stop_alarm(ROMAN_CHAT)

        self.alarm_run(check_then_stop)

        self.assertGreaterEqual(len(live), 3)

    def test_any_text_from_roman_stops_the_alarm(self):
        self.connect()

        def write():
            update = {"message": {"message_id": 9, "chat": {"id": ROMAN_CHAT, "type": "private"},
                                  "from": {"id": ROMAN}, "text": "/here"}}
            return self.channel.handle_update(update)
        pings = self.alarm_run(write)
        count = len(pings)

        self.assertEqual(self.channel._alarms, {})
        self.assertEqual(len([m for m in self.api.sent if m["text"].startswith("⏰")]), count)  # no more pings
        self.assertEqual(self.instructions, [])  # /here is not an instruction

    def test_note_without_anything_waiting_does_not_alarm(self):
        self.connect()

        self.note()

        self.assertFalse(any(m["text"].startswith("⏰") for m in self.api.sent))

    def test_long_notes_are_split_under_telegram_limit(self):
        self.assertEqual([len(p) for p in chunks("x" * 9000)], [4000, 4000, 1000])


if __name__ == "__main__":
    unittest.main()
