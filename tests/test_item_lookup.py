# What it does: Unit tests for the background item lookup — results go to the operator's note only,
#   nothing is sent to the lead.
# When it runs: `.venv/bin/python -m unittest discover tests` from operator/.
# What calls it: developer / Claude, by hand.
import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import item_lookup, webhooks
from sim.file_thread import FileThreadMessagingClient
from app.note import render_text

RESULT = {
    "match": "https://www.ikea.com/us/en/p/malm-6-drawer-dresser-white-1/",
    "candidates": [{"title": "MALM black-brown", "url": "https://www.ikea.com/us/en/p/malm-black-2/"}],
    "why": "Same dresser, different finishes.",
}


class ItemLookupTest(unittest.IsolatedAsyncioTestCase):
    async def test_result_goes_to_note_not_to_lead(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = FileThreadMessagingClient(Path(tmp) / "thread.jsonl")
            notes = []
            with mock.patch.object(item_lookup, "look_up", mock.AsyncMock(return_value=RESULT)):
                webhooks.make_item_lookup(client, notes.append)("neg-1", "IKEA MALM 6-drawer dresser")
                await asyncio.sleep(0.05)
            self.assertEqual(client.read_all(), [])
            text = render_text(notes[0])
            self.assertIn("Likely: https://www.ikea.com/us/en/p/malm-6-drawer-dresser-white-1/", text)
            self.assertIn("MALM black-brown", text)


if __name__ == "__main__":
    unittest.main()
