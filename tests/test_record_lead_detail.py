# What it does: Unit tests for the agent's record_lead_detail tool — allowed fields save,
#   system-owned fields (status) are rejected.
# When it runs: `.venv/bin/python -m unittest discover tests` from operator/.
# What calls it: developer / Claude, by hand.
import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app.db import leads
from app.tools import _record_lead_detail_impl


class RecordLeadDetailTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        patcher = mock.patch.object(leads, "LEADS_DIR", Path(tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        leads.create("lead-1")

    def test_saves_item_link_and_preferred_day(self):
        asyncio.run(_record_lead_detail_impl("lead-1", "item_link", "https://a.co/d/x"))
        asyncio.run(_record_lead_detail_impl("lead-1", "preferred_day", "Friday"))

        lead = leads.find("lead-1")
        self.assertEqual(lead.item_link, "https://a.co/d/x")
        self.assertEqual(lead.preferred_day, "Friday")

    def test_rejects_system_owned_status(self):
        result = asyncio.run(_record_lead_detail_impl("lead-1", "status", "job_complete"))

        self.assertTrue(result["is_error"])
        self.assertEqual(leads.find("lead-1").status, "new")


if __name__ == "__main__":
    unittest.main()
