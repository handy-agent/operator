# What it does: Unit tests for POST /webhooks/telegram — only calls carrying the secret given to Telegram
#   in setWebhook are handled; anyone else hitting the public URL is refused.
# When it runs: `.venv/bin/python -m unittest discover tests` from operator/.
# What calls it: developer / Claude, by hand.
import os
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from app import main


class TelegramWebhookTest(unittest.TestCase):
    def setUp(self):
        self.telegram = mock.Mock()
        for patcher in (mock.patch.object(main, "telegram", self.telegram),
                        mock.patch.dict(os.environ, {"TELEGRAM_WEBHOOK_SECRET": "s3cret"})):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client = TestClient(main.app)

    def post(self, headers):
        return self.client.post("/webhooks/telegram", json={"update_id": 1}, headers=headers)

    def test_right_secret_is_handled(self):
        self.assertEqual(self.post({"X-Telegram-Bot-Api-Secret-Token": "s3cret"}).status_code, 200)
        self.telegram.handle_soon.assert_called_once_with({"update_id": 1})

    def test_wrong_or_missing_secret_is_refused(self):
        self.assertEqual(self.post({"X-Telegram-Bot-Api-Secret-Token": "nope"}).status_code, 403)
        self.assertEqual(self.post({}).status_code, 403)
        self.telegram.handle_soon.assert_not_called()

    def test_refused_when_no_secret_is_configured(self):
        with mock.patch.dict(os.environ, {"TELEGRAM_WEBHOOK_SECRET": ""}):
            self.assertEqual(self.post({"X-Telegram-Bot-Api-Secret-Token": ""}).status_code, 403)


if __name__ == "__main__":
    unittest.main()
