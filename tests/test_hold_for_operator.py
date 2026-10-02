# What it does: Unit tests for hold_for_operator — the held "let me check" fallback is sent only if
#   the operator doesn't answer in time, and never after he answers, takes over, or a newer hold.
# When it runs: `.venv/bin/python -m unittest discover tests` from operator/.
# What calls it: developer / Claude, by hand.
import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app.db import held_replies, sessions
from sim.file_thread import FileThreadMessagingClient
from app.tools import _hold_for_operator_impl
from tests import business_env

FALLBACK = "Let me check and get back to you on that."


class HoldForOperatorTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        business_env.use(self)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        for module, attr in [(held_replies, "HELD_DIR"), (sessions, "SESSIONS_DIR")]:
            patcher = mock.patch.object(module, attr, root / attr)
            patcher.start()
            self.addCleanup(patcher.stop)
        env = mock.patch.dict(os.environ, {"OPERATOR_HOLD_SECONDS": "0.05"})
        env.start()
        self.addCleanup(env.stop)
        sessions.create("neg-1", lead_id="neg-1")
        self.client = FileThreadMessagingClient(root / "thread.jsonl")

    def sent(self):
        return [m.text for m in self.client.read_all()]

    async def test_fallback_sent_when_operator_does_not_answer(self):
        await _hold_for_operator_impl(self.client, "neg-1", FALLBACK)
        await asyncio.sleep(0.15)
        self.assertEqual(self.sent(), [FALLBACK])

    async def test_no_fallback_after_operator_answers(self):
        await _hold_for_operator_impl(self.client, "neg-1", FALLBACK)
        held_replies.clear("neg-1")  # what an operator instruction does
        await asyncio.sleep(0.15)
        self.assertEqual(self.sent(), [])

    async def test_no_fallback_after_takeover(self):
        await _hold_for_operator_impl(self.client, "neg-1", FALLBACK)
        sessions.mark_taken_over("neg-1")
        await asyncio.sleep(0.15)
        self.assertEqual(self.sent(), [])

    async def test_newer_hold_replaces_older(self):
        await _hold_for_operator_impl(self.client, "neg-1", "first")
        await _hold_for_operator_impl(self.client, "neg-1", "second")
        await asyncio.sleep(0.15)
        self.assertEqual(self.sent(), ["second"])

    async def test_fallback_cannot_contain_price(self):
        result = await _hold_for_operator_impl(self.client, "neg-1", "It's $110")
        self.assertTrue(result["is_error"])


if __name__ == "__main__":
    unittest.main()
