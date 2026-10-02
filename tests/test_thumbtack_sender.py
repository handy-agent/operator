# What it does: Unit tests for telling the agent's own Thumbtack messages apart from the owner's manual ones.
# When it runs: `.venv/bin/python -m unittest discover tests` from operator/.
# What calls it: developer / Claude, by hand.
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app.db import sent_messages
from app.messaging.thumbtack import _sender


class ThumbtackSenderTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        patcher = mock.patch.object(sent_messages, "SENT_DIR", Path(tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_labels_lead_agent_and_operator(self):
        sent_messages.record("neg-1", "Could you send a link?\nThanks")
        sent = sent_messages.texts("neg-1")

        self.assertEqual(_sender({"from": "Customer", "text": "hi"}, sent), "lead")
        self.assertEqual(_sender({"from": "Pro", "text": "Could you send a link?\nThanks"}, sent), "agent")
        self.assertEqual(_sender({"from": "Pro", "text": "Friday works. $110"}, sent), "operator")


if __name__ == "__main__":
    unittest.main()
