# What it does: Unit tests for replying like a person when the lead writes again mid-reply — the send
#   is refused and the new text shown to the agent, and a follow-up turn is skipped once answered.
# When it runs: `.venv/bin/python -m unittest discover tests` from operator/.
# What calls it: developer / Claude, by hand.
import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import webhooks
from app.db import leads, sessions
from sim.file_thread import FileThreadMessagingClient
from app.tools import LeadWatch, _send_message_impl
from tests import business_env


class LeadWroteMeanwhileTest(unittest.TestCase):
    def setUp(self):
        business_env.use(self)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.client = FileThreadMessagingClient(self.root / "thread.jsonl")

    def test_send_refused_until_agent_has_seen_new_lead_message(self):
        self.client.add_lead_message("Need 2 beds assembled")
        watch = LeadWatch(asyncio.run(self.client.get_messages("neg-1")))
        self.client.add_lead_message("Also Friday works")  # arrives while the agent is writing

        refused = asyncio.run(_send_message_impl(self.client, "neg-1", "Could you send a link?", watch=watch))
        self.assertTrue(refused["is_error"])
        self.assertIn("Also Friday works", refused["content"][0]["text"])

        sent = asyncio.run(_send_message_impl(self.client, "neg-1", "Thanks! Could you send a link?", watch=watch))
        self.assertNotIn("is_error", sent)
        self.assertEqual([m.sender for m in self.client.read_all()], ["lead", "lead", "agent"])

    def test_follow_up_turn_skipped_when_last_message_already_answered(self):
        for module, attr in [(leads, "LEADS_DIR"), (sessions, "SESSIONS_DIR")]:
            patcher = mock.patch.object(module, attr, self.root / attr)
            patcher.start()
            self.addCleanup(patcher.stop)
        leads.create("neg-1")
        sessions.create("neg-1", lead_id="neg-1")
        self.client.add_lead_message("Also Friday works")
        asyncio.run(self.client.send_message("neg-1", "Thanks! Friday noted."))

        with mock.patch.object(webhooks.agent, "run_agent_turn", mock.AsyncMock()) as run_turn:
            asyncio.run(webhooks.run_batched_turn("neg-1", ["Also Friday works"], self.client))
        run_turn.assert_not_called()


if __name__ == "__main__":
    unittest.main()
