# What it does: Unit tests for the background estimate (decided 2026-10-02): it starts alongside the reply
#   turn (never delays it), posts its own note to the operator only when there's a new estimate, and
#   nothing goes to the lead.
# When it runs: `.venv/bin/python -m unittest discover tests` from operator/.
# What calls it: developer / Claude, by hand.
import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import agent, estimator, webhooks
from app.db import estimates, leads, sessions
from app.note import render_text
from sim.file_thread import FileThreadMessagingClient


class EstimatorTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        for module, attr in [(leads, "LEADS_DIR"), (sessions, "SESSIONS_DIR"), (estimates, "ESTIMATES_DIR")]:
            patcher = mock.patch.object(module, attr, Path(tmp.name) / attr)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client = FileThreadMessagingClient(Path(tmp.name) / "thread.jsonl")
        leads.create("neg-1")
        sessions.create("neg-1", "neg-1")

    async def test_new_estimate_goes_to_a_note_not_to_the_lead(self):
        async def fake_run(lead_id, client):
            estimates.create(lead_id, "furniture_assembly", price_text="$175 (confidence 6/10)", suggested=175)

        notes = []
        with mock.patch.object(estimator, "run", fake_run):
            webhooks.make_estimator(self.client, notes.append)("neg-1")
            await asyncio.sleep(0.05)
        self.assertEqual(self.client.read_all(), [])
        self.assertIn("$175", render_text(notes[0]))

    async def test_no_note_when_the_latest_estimate_was_already_decided(self):
        estimates.create("neg-1", "furniture_assembly", price_text="$175", suggested=175)
        estimates.record_decision("neg-1", 340)
        notes = []
        with mock.patch.object(estimator, "run", mock.AsyncMock()):
            webhooks.make_estimator(self.client, notes.append)("neg-1")
            await asyncio.sleep(0.05)
        self.assertEqual(notes, [])

    async def test_no_note_when_nothing_changed(self):
        notes = []
        with mock.patch.object(estimator, "run", mock.AsyncMock()):
            webhooks.make_estimator(self.client, notes.append)("neg-1")
            await asyncio.sleep(0.05)
        self.assertEqual(notes, [])

    async def test_estimate_starts_before_the_reply_turn_finishes(self):
        self.client.add_lead_message("assemble my bed frame")
        started = []

        async def slow_turn(**kwargs):
            self.assertEqual(started, ["neg-1"])  # already running while the reply is being written
            return None

        with mock.patch.object(agent, "run_agent_turn", slow_turn):
            await webhooks.run_batched_turn("neg-1", ["assemble my bed frame"], self.client,
                                            start_estimate=started.append)


if __name__ == "__main__":
    unittest.main()
