# What it does: Test helper — serves the real seed catalog (db/seed/, converted by app/db/seed.py) to
#   app/catalog.py without a store. The store itself is tested in test_records_dynamo.py / test_seed.py;
#   this keeps catalog-heavy tests fast (reading ~2,900 records per call from files would be slow).
# When it runs: setUp of tests that price or search jobs.
# What calls it: tests/test_estimate.py, tests/test_estimate_decisions.py, tests/test_prices_api.py.
import unittest
from functools import lru_cache
from unittest import mock

from app import catalog
from app.db import seed


@lru_cache(maxsize=None)
def _by_kind() -> dict[str, dict[str, dict]]:
    return {kind_dir.name: by_id for kind_dir, by_id in seed.catalog_records(seed.SEED_DIR).items()}


def use(test: unittest.TestCase) -> None:
    kinds = _by_kind()
    for name, fake in [
        ("subservices", lambda: [kinds["subservices"][i] for i in sorted(kinds["subservices"])]),
        ("subservice", lambda subservice_id: kinds["subservices"].get(subservice_id)),
        ("multipliers", lambda: [kinds["multipliers"][i] for i in sorted(kinds["multipliers"])]),
    ]:
        patcher = mock.patch.object(catalog, name, fake)
        patcher.start()
        test.addCleanup(patcher.stop)
