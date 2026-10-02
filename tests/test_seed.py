# What it does: Unit tests for seeding the record store from db/seed/ (app/db/seed.py): the catalog's
#   services, subservices and multipliers become records, and reseeding drops what the seed no longer has.
# When it runs: `.venv/bin/python -m unittest discover tests` from operator/.
# What calls it: developer / Claude, by hand.
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import catalog
from app.db import seed


class SeedTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.seed_dir = Path(tmp.name) / "seed"
        self.seed_dir.mkdir()
        store = Path(tmp.name) / "store"
        for attr in ("SERVICES_DIR", "SUBSERVICES_DIR", "MULTIPLIERS_DIR"):
            patcher = mock.patch.object(catalog, attr, store / getattr(catalog, attr).name)
            patcher.start()
            self.addCleanup(patcher.stop)

    def write(self, services: list, multipliers: list) -> None:
        (self.seed_dir / "services.json").write_text(json.dumps(services))
        (self.seed_dir / "multipliers.json").write_text(json.dumps(multipliers))

    def test_catalog_items_become_records(self):
        self.write(
            [{"pk": "SERVICE#handyman", "sk": "META", "name": "Handyman"},
             {"pk": "SERVICE#handyman", "sk": "SUB#tv_mounting", "name": "TV", "pricing": {"model": "flat", "price": 99.5}}],
            [{"pk": "MULT#distance", "sk": "META", "kind": "tiers"}],
        )
        self.assertEqual(seed.seed(self.seed_dir), {"services": 1, "subservices": 1, "multipliers": 1})
        self.assertEqual(catalog.subservice("tv_mounting"), {
            "id": "tv_mounting", "service_id": "handyman", "name": "TV", "pricing": {"model": "flat", "price": 99.5}})
        self.assertEqual(catalog.multipliers(), [{"id": "distance", "kind": "tiers"}])

    def test_reseed_drops_removed_items(self):
        self.write([{"pk": "SERVICE#h", "sk": "SUB#a"}, {"pk": "SERVICE#h", "sk": "SUB#b"}], [])
        seed.seed(self.seed_dir)
        self.write([{"pk": "SERVICE#h", "sk": "SUB#a"}], [])
        seed.seed(self.seed_dir)
        self.assertEqual([s["id"] for s in catalog.subservices()], ["a"])


if __name__ == "__main__":
    unittest.main()
