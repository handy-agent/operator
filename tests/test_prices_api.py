# What it does: Unit tests for the /prices endpoint filters (no filters = everything).
# When it runs: `.venv/bin/python -m unittest discover tests` from operator/.
# What calls it: developer / Claude, by hand.
import unittest

from fastapi.testclient import TestClient

from app.main import app
from app.prices_api import rows
from tests import seeded_catalog


class PricesApiTest(unittest.TestCase):
    def setUp(self):
        seeded_catalog.use(self)
        self.client = TestClient(app)

    def test_no_filters_returns_everything(self):
        body = self.client.get("/prices").json()
        self.assertEqual(body["count"], len(rows()))
        self.assertGreater(body["count"], 3)

    def test_filters_combine(self):
        body = self.client.get("/prices", params={"service": "handyman", "curated": "true"}).json()
        self.assertTrue(body["prices"])
        self.assertTrue(all(r["service"] == "handyman" and r["curated"] for r in body["prices"]))

    def test_keyword_and_max_price(self):
        body = self.client.get("/prices", params={"q": "furniture assembly", "max_price": 130}).json()
        self.assertTrue(body["prices"])
        self.assertTrue(all(
            "furniture" in f"{r['subservice']} {r['name']} {r['service']}".lower() and r["baseline"] <= 130
            for r in body["prices"]
        ))

    def test_report_renders_html(self):
        response = self.client.get("/prices/report", params={"q": "tv"})
        self.assertIn("<table>", response.text)


if __name__ == "__main__":
    unittest.main()
