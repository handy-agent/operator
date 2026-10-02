# What it does: Unit tests for the agent's pause_lead / resume_lead tools (operator's plain-words control).
# When it runs: `.venv/bin/python -m unittest discover tests` from operator/.
# What calls it: developer / Claude, by hand.
import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app.db import sessions
from app.tools import _pause_lead_impl, _resume_lead_impl


class PauseResumeToolsTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        patcher = mock.patch.object(sessions, "SESSIONS_DIR", Path(tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        sessions.create("neg-1", lead_id="neg-1")

    def test_pause_then_resume(self):
        asyncio.run(_pause_lead_impl("neg-1"))
        self.assertTrue(sessions.find("neg-1").taken_over)

        asyncio.run(_resume_lead_impl("neg-1"))
        self.assertFalse(sessions.find("neg-1").taken_over)


if __name__ == "__main__":
    unittest.main()
