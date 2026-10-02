# What it does: Unit tests for unwrapping a real Thumbtack webhook delivery into the message.
# When it runs: `.venv/bin/python -m unittest discover tests` from operator/.
# What calls it: developer / Claude, by hand.
import unittest

from app.webhooks import message_from_event

# Shape of a real MessageCreatedV4 delivery (2026-09-30), names and IDs made up.
MESSAGE_EVENT = {
    "event": {"eventType": "MessageCreatedV4", "description": "", "webhookID": "w1", "triggeredAt": "2026-09-30T09:50:12Z"},
    "data": {
        "messageID": "m1",
        "negotiationID": "n1",
        "customer": {"customerID": "c1", "displayName": "Test Lead"},
        "business": {"businessID": "b1", "displayName": "Test Business"},
        "from": "Customer",
        "text": "I have a smoker to fix",
        "sentAt": "2026-09-30T09:49:51Z",
    },
}


class MessageFromEventTest(unittest.TestCase):
    def test_returns_the_message_data(self):
        message = message_from_event(MESSAGE_EVENT)
        self.assertEqual(message["negotiationID"], "n1")
        self.assertEqual(message["text"], "I have a smoker to fix")
        self.assertEqual(message["customer"]["displayName"], "Test Lead")

    def test_other_event_types_are_skipped(self):
        self.assertIsNone(message_from_event({"event": {"eventType": "NegotiationCreatedV4"}, "data": {}}))

    def test_body_without_envelope_is_skipped(self):
        self.assertIsNone(message_from_event({"negotiationID": "n1", "text": "hi"}))


if __name__ == "__main__":
    unittest.main()
