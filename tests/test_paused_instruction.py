# What it does: Unit tests for instructions while a lead is paused (decided 2026-09-25): the operator talks
#   to the lead himself then, so the agent answers him but has no tool that reaches the lead.
# When it runs: `.venv/bin/python -m unittest discover tests` from operator/.
# What calls it: developer / Claude, by hand.
import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import agent
from app.db import sessions
from sim.file_thread import FileThreadMessagingClient
from tests import business_env


class PausedInstructionTest(unittest.TestCase):
    def setUp(self):
        business_env.use(self)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        patcher = mock.patch.object(sessions, "SESSIONS_DIR", Path(tmp.name) / "sessions")
        patcher.start()
        self.addCleanup(patcher.stop)
        sessions.create("neg-1", lead_id="neg-1")
        self.client = FileThreadMessagingClient(Path(tmp.name) / "thread.jsonl")
        self.client.add_lead_message("hi")

    def run_instruction(self):
        seen = {}

        async def fake_query(prompt, options):
            seen["prompt"], seen["options"] = prompt, options
            return
            yield

        with mock.patch.object(agent, "query", fake_query):
            asyncio.run(agent.run_agent_turn("neg-1", "neg-1", "say hi", self.client, from_operator=True))
        return seen

    def test_paused_lead_gets_no_lead_facing_tools(self):
        sessions.mark_taken_over("neg-1")

        seen = self.run_instruction()

        options = seen["options"]
        self.assertFalse(agent.LEAD_FACING_TOOLS & set(options.allowed_tools))
        self.assertEqual(set(options.disallowed_tools), agent.LEAD_FACING_TOOLS)
        self.assertIn("This lead is paused", seen["prompt"])

    def test_active_lead_keeps_them(self):
        seen = self.run_instruction()

        self.assertTrue(agent.LEAD_FACING_TOOLS <= set(seen["options"].allowed_tools))
        self.assertNotIn("This lead is paused", seen["prompt"])


if __name__ == "__main__":
    unittest.main()
