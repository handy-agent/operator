# What it does: Unit tests for estimate confidence and for recording the owner's decision on a draft
#   (approved as suggested vs. changed), including "approve" with no number.
# When it runs: `.venv/bin/python -m unittest discover tests` from operator/.
# What calls it: developer / Claude, by hand.
import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app.db import estimates
from app.estimate import EstimateInput, estimate
from sim.file_thread import FileThreadMessagingClient
from app.tools import _send_message_impl
from tests import seeded_catalog
from tests import business_env


class ConfidenceTest(unittest.TestCase):
    def setUp(self):
        seeded_catalog.use(self)

    def test_hand_set_known_inputs_scores_higher_than_imported_unknowns(self):
        curated = estimate(EstimateInput("outdoor_furniture_assembly", 2, state="TX", distance_miles=5))
        imported = estimate(EstimateInput("ceiling_fan_install", 1))
        self.assertGreater(curated.confidence, imported.confidence)
        self.assertTrue(1 <= imported.confidence <= 10)
        self.assertIn("distance unknown", imported.confidence_why)


class DecisionTest(unittest.TestCase):
    def setUp(self):
        business_env.use(self)
        seeded_catalog.use(self)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        patcher = mock.patch.object(estimates, "ESTIMATES_DIR", Path(tmp.name) / "estimates")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = FileThreadMessagingClient(Path(tmp.name) / "thread.jsonl")
        estimates.create("neg-1", "furniture_assembly", suggested=140, confidence=8)

    def send(self, text, approved):
        return asyncio.run(_send_message_impl(self.client, "neg-1", text, frozenset(approved)))

    def test_approved_as_suggested(self):
        self.send("It'd be $140. Does Friday work?", {"140"})  # "approve" -> draft price allowed
        e = estimates.list_for_lead("neg-1")[0]
        self.assertEqual((e.status, e.approved_price), ("approved", 140))

    def test_roman_changed_price(self):
        self.send("It'd be $160. Does Friday work?", {"160", "140"})
        e = estimates.list_for_lead("neg-1")[0]
        self.assertEqual((e.status, e.approved_price), ("changed", 160))


if __name__ == "__main__":
    unittest.main()
