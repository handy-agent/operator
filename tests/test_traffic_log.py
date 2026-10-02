# What it does: Unit tests for the Thumbtack traffic log (inbound webhooks + outbound API calls).
# When it runs: `.venv/bin/python -m unittest discover tests` from operator/.
# What calls it: developer / Claude, by hand.
import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import httpx

from app.db import records, sent_messages, traffic_log
from app.messaging.thumbtack import ThumbtackMessagingClient


def saved_entries() -> list[dict]:
    return records.load_all(traffic_log.TRAFFIC_DIR)


class TrafficLogTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        patcher = mock.patch.object(traffic_log, "TRAFFIC_DIR", Path(tmp.name) / "traffic")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_saves_request_and_response(self):
        traffic_log.save("inbound", {"method": "POST", "url": "/w", "headers": {}, "body": {"a": 1}},
                         {"status": 200, "body": {"handled": True}})
        [entry] = saved_entries()
        self.assertEqual(entry["direction"], "inbound")
        self.assertEqual(entry["request"]["body"], {"a": 1})
        self.assertEqual(entry["response"]["status"], 200)
        self.assertIsNone(entry["error"])

    def test_redacts_authorization(self):
        traffic_log.save("outbound", {"method": "GET", "url": "/x", "headers": {"Authorization": "Bearer secret"}})
        [entry] = saved_entries()
        self.assertEqual(entry["request"]["headers"]["Authorization"], "<redacted>")
        self.assertNotIn("secret", json.dumps(entry))

    def test_body_value_parses_json_and_keeps_text(self):
        self.assertEqual(traffic_log.body_value(b'{"a": 1}'), {"a": 1})
        self.assertEqual(traffic_log.body_value(b"plain"), "plain")
        self.assertIsNone(traffic_log.body_value(b""))


class ThumbtackClientLoggingTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        for patcher in (mock.patch.object(traffic_log, "TRAFFIC_DIR", Path(tmp.name) / "traffic"),
                        mock.patch.object(sent_messages, "SENT_DIR", Path(tmp.name) / "sent")):
            patcher.start()
            self.addCleanup(patcher.stop)

    def fake_http(self, status: int, body: dict):
        transport = httpx.MockTransport(lambda request: httpx.Response(status, json=body))
        real_client = httpx.AsyncClient
        return mock.patch("app.messaging.thumbtack.httpx.AsyncClient",
                          lambda *a, **kw: real_client(*a, transport=transport, **kw))

    def test_logs_a_successful_send(self):
        client = ThumbtackMessagingClient("https://api.example", "tok")
        with self.fake_http(201, {"messageID": "m1"}):
            asyncio.run(client.send_message("n1", "hello"))
        [entry] = saved_entries()
        self.assertEqual(entry["direction"], "outbound")
        self.assertEqual(entry["request"]["url"], "https://api.example/api/v4/negotiations/n1/messages")
        self.assertEqual(entry["request"]["body"], {"text": "hello"})
        self.assertEqual(entry["request"]["headers"]["authorization"], "<redacted>")
        self.assertEqual(entry["response"]["status"], 201)
        self.assertEqual(entry["response"]["body"], {"messageID": "m1"})

    def test_logs_an_error_response_before_raising(self):
        client = ThumbtackMessagingClient("https://api.example", "tok")
        with self.fake_http(401, {"error": "unauthorized"}), self.assertRaises(httpx.HTTPStatusError):
            asyncio.run(client.get_messages("n1"))
        [entry] = saved_entries()
        self.assertEqual(entry["response"]["status"], 401)
        self.assertEqual(entry["response"]["body"], {"error": "unauthorized"})


if __name__ == "__main__":
    unittest.main()
