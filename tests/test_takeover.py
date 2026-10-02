# What it does: Unit tests for takeover — the operator replying by hand pauses the agent on that lead,
#   the agent's own echoed message doesn't, and resume hands the lead back.
# When it runs: `.venv/bin/python -m unittest discover tests` from operator/.
# What calls it: developer / Claude, by hand.
import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import webhooks
from app.db import idempotency, leads, sent_messages, sessions, statuses
from sim.file_thread import FileThreadMessagingClient


class TakeoverTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        for module, attr in [(leads, "LEADS_DIR"), (sessions, "SESSIONS_DIR"), (statuses, "STATUSES_DIR"),
                             (idempotency, "PROCESSED_DIR"), (sent_messages, "SENT_DIR")]:
            patcher = mock.patch.object(module, attr, root / attr)
            patcher.start()
            self.addCleanup(patcher.stop)
        run_turn = mock.patch.object(webhooks.agent, "run_agent_turn", mock.AsyncMock(return_value=None))
        self.run_turn = run_turn.start()
        self.addCleanup(run_turn.stop)
        self.client = FileThreadMessagingClient(root / "thread.jsonl")

    def event(self, message_id, sender, text):
        payload = {"negotiationID": "neg-1", "messageID": message_id, "from": sender, "text": text}
        return asyncio.run(webhooks.handle_thumbtack_event(payload, messaging_client=self.client))

    def test_manual_reply_pauses_agent_until_resume(self):
        self.event("m1", "Customer", "Need a dresser built")
        self.assertEqual(self.run_turn.call_count, 1)

        self.event("m2", "Pro", "Friday works. $110")
        self.assertTrue(sessions.find("neg-1").taken_over)

        self.event("m3", "Customer", "What time?")
        self.assertEqual(self.run_turn.call_count, 1)

        sessions.resume("neg-1")
        self.event("m4", "Customer", "Hello?")
        self.assertEqual(self.run_turn.call_count, 2)

    def test_only_a_new_leads_first_message_skips_the_human_delay(self):
        scheduler = mock.Mock()
        for message_id, text in [("m1", "Need a dresser built"), ("m2", "Friday?")]:
            payload = {"negotiationID": "neg-1", "messageID": message_id, "from": "Customer", "text": text}
            asyncio.run(webhooks.handle_thumbtack_event(payload, messaging_client=self.client, scheduler=scheduler))

        self.assertEqual([c.kwargs["immediate"] for c in scheduler.add.call_args_list], [True, False])

    def test_agent_own_echo_does_not_pause(self):
        self.event("m1", "Customer", "Need a dresser built")
        sent_messages.record("neg-1", "Could you send a link?")

        self.event("m2", "Pro", "Could you send a link?")

        self.assertFalse(sessions.find("neg-1").taken_over)


if __name__ == "__main__":
    unittest.main()
