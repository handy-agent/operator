# What it does: Unit tests for the catalog-based price calculator and the propose_estimate gate
#   (no estimate without a link or photos).
# When it runs: `.venv/bin/python -m unittest discover tests` from operator/.
# What calls it: developer / Claude, by hand.
import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app.db import estimates, leads
from app.estimate import EstimateInput, base_price, estimate
from app.tools import _propose_estimate_impl, _search_catalog_impl
from tests import business_env, seeded_catalog


class BasePriceTest(unittest.TestCase):
    def test_per_item_table_and_beyond_it(self):
        table = {"model": "per_item", "qty_prices": {"1": 120, "2": 160, "3": 200}}
        self.assertEqual(base_price(table, 2), 160)
        self.assertEqual(base_price(table, 5), 280)  # keeps adding the last step (+40)

    def test_per_item_unit_price_with_minimum(self):
        pricing = {"model": "per_item", "unit_price": 90, "min_price": 125}
        self.assertEqual(base_price(pricing, 1), 125)
        self.assertEqual(base_price(pricing, 2), 180)

    def test_hourly_minimum_and_per_unit_minimum(self):
        self.assertEqual(base_price({"model": "hourly", "rate": 65, "min_hours": 1}, 0.5), 65)
        self.assertEqual(base_price({"model": "per_unit", "unit": "sq_ft", "rate": 3.5, "min": 200}, 100), 350)


class EstimateTest(unittest.TestCase):
    def setUp(self):
        seeded_catalog.use(self)

    def test_multipliers_compound_then_add_and_round_to_5(self):
        # 2 raised beds: base 180 × distance 1.3 = 234, + lead cost 20 = 254 -> 255
        result = estimate(EstimateInput("outdoor_furniture_assembly", 2, state="TX", distance_miles=32))
        self.assertEqual(result.suggested, 255)

    def test_option_multiplier_and_unknown_distance_reported(self):
        # 1 item without instructions: 120 × 1.3 = 156, + 20 = 176 -> 175
        result = estimate(EstimateInput("furniture_assembly", 1, {"instructions": "without"}))
        self.assertEqual(result.suggested, 175)
        self.assertIn("distance", result.unknown)


class ProposeEstimateTest(unittest.TestCase):
    def setUp(self):
        business_env.use(self)
        seeded_catalog.use(self)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        for module, attr in [(leads, "LEADS_DIR"), (estimates, "ESTIMATES_DIR")]:
            patcher = mock.patch.object(module, attr, Path(tmp.name) / attr)
            patcher.start()
            self.addCleanup(patcher.stop)
        leads.create("neg-1")

    def test_rough_estimate_without_link_or_photos(self):
        result = asyncio.run(_propose_estimate_impl("neg-1", "furniture_assembly", 1))
        self.assertFalse(result.get("is_error"))
        self.assertIn("Rough", result["content"][0]["text"])
        self.assertTrue(estimates.latest_draft("neg-1").rough)

    def test_new_estimate_replaces_the_previous_draft(self):
        asyncio.run(_propose_estimate_impl("neg-1", "furniture_assembly", 1))
        lead = leads.find("neg-1")
        lead.item_link = "https://a.co/d/x"
        leads.save(lead)
        asyncio.run(_propose_estimate_impl("neg-1", "furniture_assembly", 2))
        by_status = sorted((e.status, e.rough) for e in estimates.list_for_lead("neg-1"))
        self.assertEqual(by_status, [("draft", False), ("superseded", True)])

    def test_same_estimate_again_is_unchanged_even_after_roman_decided(self):
        asyncio.run(_propose_estimate_impl("neg-1", "furniture_assembly", 1))
        estimates.record_decision("neg-1", 340)
        result = asyncio.run(_propose_estimate_impl("neg-1", "furniture_assembly", 1))
        self.assertIn("unchanged", result["content"][0]["text"])
        self.assertEqual(len(estimates.list_for_lead("neg-1")), 1)
        self.assertIsNone(estimates.latest_draft("neg-1"))  # the owner's $340 stays the answer

    def test_drafts_once_link_saved(self):
        lead = leads.find("neg-1")
        lead.item_link = "https://a.co/d/x"
        leads.save(lead)
        result = asyncio.run(_propose_estimate_impl("neg-1", "furniture_assembly", 1))
        self.assertIn("Suggested $140", result["content"][0]["text"])


class SearchCatalogTest(unittest.TestCase):
    def setUp(self):
        seeded_catalog.use(self)

    def test_finds_outdoor_assembly_for_raised_beds(self):
        text = asyncio.run(_search_catalog_impl("outdoor raised garden bed assembly"))["content"][0]["text"]
        self.assertTrue(text.startswith("outdoor_furniture_assembly"))


if __name__ == "__main__":
    unittest.main()
