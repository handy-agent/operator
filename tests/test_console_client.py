# What it does: Unit tests for ConsoleMessagingClient (the simulator's fake messaging client).
# When it runs: `.venv/bin/python -m unittest discover tests` from operator/.
# What calls it: developer / Claude, by hand.
import asyncio
import unittest

from sim.console_client import ConsoleMessagingClient


class ConsoleMessagingClientTest(unittest.TestCase):
    def test_keeps_thread_in_order_with_senders(self):
        client = ConsoleMessagingClient()
        client.add_lead_message("Need a faucet fixed")
        asyncio.run(client.send_message("sim-1", "Sure, which room is it in?"))

        messages = asyncio.run(client.get_messages("sim-1"))

        self.assertEqual([m.sender for m in messages], ["lead", "agent"])
        self.assertEqual(messages[1].text, "Sure, which room is it in?")
        self.assertEqual(len({m.message_id for m in messages}), 2)

    def test_manual_reply_is_labeled_operator(self):
        client = ConsoleMessagingClient()
        client.add_lead_message("Friday?")
        client.add_operator_message("Friday works for me. I can do it for $110")

        messages = asyncio.run(client.get_messages("sim-1"))

        self.assertEqual(messages[-1].sender, "operator")
        self.assertEqual(messages[-1].text, "Friday works for me. I can do it for $110")


if __name__ == "__main__":
    unittest.main()
