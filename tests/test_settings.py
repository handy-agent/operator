# What it does: Unit tests for per-customer settings (app/settings.py): defaults, a customer's own
#   overrides (only for them), validation, going back to the default, and the places that read them.
# When it runs: `.venv/bin/python -m unittest discover tests` from operator/.
# What calls it: developer / Claude, by hand.
import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import settings, tools, webhooks
from app.db import accounts, idempotency, leads, sessions, statuses
from app.reply_timing import delays_from_settings
from sim.file_thread import FileThreadMessagingClient


class SettingsTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        for module, attr in [(accounts, "ACCOUNTS_DIR"), (leads, "LEADS_DIR"), (sessions, "SESSIONS_DIR"),
                             (statuses, "STATUSES_DIR"), (idempotency, "PROCESSED_DIR")]:
            patcher = mock.patch.object(module, attr, root / attr)
            patcher.start()
            self.addCleanup(patcher.stop)
        accounts.find_or_create("atx", "ATX Handy Pros")
        accounts.find_or_create("other", "Other Pro")
        leads.create("neg-1", account_id="atx")
        self.root = root

    def test_defaults_until_a_customer_changes_something(self):
        self.assertEqual(settings.for_account("atx"), settings.DEFAULTS)

        settings.update("atx", {"alarm_for_seconds": "180", "first_reply_immediate": "off"})

        self.assertEqual(settings.for_account("atx")["alarm_for_seconds"], 180)
        self.assertIs(settings.for_account("atx")["first_reply_immediate"], False)
        self.assertEqual(settings.for_account("other"), settings.DEFAULTS)  # only that customer
        self.assertEqual(settings.for_lead("neg-1")["alarm_for_seconds"], 180)

    def test_back_to_default(self):
        settings.update("atx", {"alarm_for_seconds": "180"})
        settings.update("atx", {"alarm_for_seconds": "default"})

        self.assertEqual(accounts.find("atx").settings, {})

    def test_bad_values_are_refused(self):
        for changes in ({"nope": "1"}, {"alarm_for_seconds": "-5"}, {"alarm_for_seconds": "abc"},
                        {"first_reply_immediate": "maybe"}):
            with self.assertRaises(ValueError):
                settings.update("atx", changes)

    def test_reply_timing_and_hold_follow_the_customer(self):
        settings.update("atx", {"reply_delay_min_seconds": "5", "reply_delay_max_seconds": "9",
                                "reply_max_wait_seconds": "30", "operator_hold_seconds": "90"})

        self.assertEqual(delays_from_settings(settings.for_lead("neg-1")), {"delay_min": 5, "delay_max": 9, "max_wait": 30})
        with mock.patch.dict(os.environ, {"OPERATOR_HOLD_SECONDS": ""}):
            self.assertEqual(tools.hold_seconds("neg-1"), 90)

    def test_first_reply_delay_can_be_turned_back_on(self):
        settings.update("atx", {"first_reply_immediate": "off"})
        scheduler = mock.Mock()
        client = FileThreadMessagingClient(self.root / "t.jsonl")

        for negotiation_id, account_id in [("new-1", "atx"), ("new-2", "other")]:  # both brand-new leads
            payload = {"negotiationID": negotiation_id, "messageID": negotiation_id, "from": "Customer", "text": "hi"}
            asyncio.run(webhooks.handle_thumbtack_event(payload, client, scheduler, account_id=account_id))

        self.assertEqual([c.kwargs["immediate"] for c in scheduler.add.call_args_list], [False, True])


if __name__ == "__main__":
    unittest.main()
