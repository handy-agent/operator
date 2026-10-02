# What it does: Unit tests for send_message's price guard — prices are blocked unless every amount
#   was given by the owner in this turn's instruction.
# When it runs: `.venv/bin/python -m unittest discover tests` from operator/.
# What calls it: developer / Claude, by hand.
import asyncio
import tempfile
import unittest
from pathlib import Path

from sim.file_thread import FileThreadMessagingClient
from app.tools import _send_message_impl, instruction_amounts, price_amounts
from tests import business_env


class SendMessagePriceGuardTest(unittest.TestCase):
    def setUp(self):
        business_env.use(self)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.client = FileThreadMessagingClient(Path(tmp.name) / "thread.jsonl")

    def send(self, text, approved=frozenset()):
        return asyncio.run(_send_message_impl(self.client, "sim-1", text, approved))

    def test_blocks_price_without_approval(self):
        self.assertTrue(self.send("It'll be $110")["is_error"])

    def test_allows_price_operator_approved(self):
        result = self.send("It'll be $110, see you Friday", price_amounts("approve $110 Friday 3pm"))
        self.assertNotIn("is_error", result)

    def test_blocks_different_price_than_approved(self):
        self.assertTrue(self.send("It'll be $150", price_amounts("approve $110"))["is_error"])

    def test_blocks_dollars_word_without_amount(self):
        self.assertTrue(self.send("About a hundred dollars", price_amounts("approve $110"))["is_error"])

    def test_normalizes_commas(self):
        self.assertEqual(price_amounts("$1,100 or $ 95.50"), frozenset({"1100", "95.50"}))

    def test_operator_bare_number_approves_dollar_price(self):
        result = self.send("It'll be $100", instruction_amounts("Friday works, 100"))
        self.assertNotIn("is_error", result)

    def test_sign_off_only_on_first_message(self):
        first = self.send("Hi, happy to help.\nSam, Test Handy Co")
        self.assertNotIn("is_error", first)

        again = self.send("Thanks!\nSam, Test Handy Co")
        self.assertTrue(again["is_error"])


if __name__ == "__main__":
    unittest.main()
