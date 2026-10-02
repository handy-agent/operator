# What it does: Unit tests for FileThreadMessagingClient — two clients on the same file see one thread.
# When it runs: `.venv/bin/python -m unittest discover tests` from operator/.
# What calls it: developer / Claude, by hand.
import asyncio
import tempfile
import unittest
from pathlib import Path

from sim.file_thread import FileThreadMessagingClient


class FileThreadMessagingClientTest(unittest.TestCase):
    def test_two_clients_share_one_thread_with_senders(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "thread.jsonl"
            chat, notes = FileThreadMessagingClient(path), FileThreadMessagingClient(path)

            chat.add_lead_message("Need a dresser built")
            asyncio.run(chat.send_message("sim-1", "Could you send a link?\nThanks"))
            chat.add_operator_message("Friday works. $110")

            messages = asyncio.run(notes.get_messages("sim-1"))
            self.assertEqual([m.sender for m in messages], ["lead", "agent", "operator"])
            self.assertEqual(messages[1].text, "Could you send a link?\nThanks")


if __name__ == "__main__":
    unittest.main()
