# What it does: Unit tests for the DynamoDB record store (app/db/records_dynamo.py) against moto's
#   in-memory DynamoDB — same calls as the file store: save/load/exists/list_ids/delete/append_line/read_lines.
# When it runs: `.venv/bin/python -m unittest discover tests` from operator/.
# What calls it: developer / Claude, by hand.
import os
import unittest
from pathlib import Path
from unittest import mock

from moto import mock_aws

from app.db import dynamo_table, records_dynamo

LEADS = Path("/anywhere/leads")
STATUSES = Path("/anywhere/statuses")


class RecordsDynamoTest(unittest.TestCase):
    def setUp(self):
        env = mock.patch.dict(os.environ, {"DYNAMODB_TABLE": "operator-test", "AWS_REGION": "us-east-1",
                                           "AWS_ACCESS_KEY_ID": "test", "AWS_SECRET_ACCESS_KEY": "test"})
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("DYNAMODB_ENDPOINT_URL", None)  # never reach a real DynamoDB; restored by env.stop
        dynamo_table._resource.cache_clear()
        self.addCleanup(dynamo_table._resource.cache_clear)
        aws = mock_aws()
        aws.start()
        self.addCleanup(aws.stop)
        dynamo_table.create()

    def test_save_then_load_round_trips_fields(self):
        fields = {"lead_id": "1", "price": 249.5, "qty": 2, "taken_over": False, "note": None,
                  "address": {"zip": "78641"}, "photos": ["a.jpg"], "empty": ""}
        records_dynamo.save(LEADS, "1", fields)
        self.assertEqual(records_dynamo.load(LEADS, "1"), fields)

    def test_load_missing_is_none(self):
        self.assertIsNone(records_dynamo.load(LEADS, "nope"))

    def test_save_replaces_whole_record(self):
        records_dynamo.save(LEADS, "1", {"a": 1, "b": 2})
        records_dynamo.save(LEADS, "1", {"a": 3})
        self.assertEqual(records_dynamo.load(LEADS, "1"), {"a": 3})

    def test_exists_and_delete(self):
        records_dynamo.save(LEADS, "1", {"a": 1})
        self.assertTrue(records_dynamo.exists(LEADS, "1"))
        records_dynamo.delete(LEADS, "1")
        self.assertFalse(records_dynamo.exists(LEADS, "1"))
        records_dynamo.delete(LEADS, "1")  # deleting a missing record is fine

    def test_list_ids_only_that_kind_sorted(self):
        records_dynamo.save(LEADS, "b", {})
        records_dynamo.save(LEADS, "a", {})
        records_dynamo.save(Path("/anywhere/sessions"), "c", {})
        self.assertEqual(records_dynamo.list_ids(LEADS), ["a", "b"])

    def test_append_line_then_read_lines_in_order(self):
        records_dynamo.append_line(STATUSES, "1", "first")
        records_dynamo.append_line(STATUSES, "1", "second")
        self.assertEqual(records_dynamo.read_lines(STATUSES, "1"), ["first", "second"])
        self.assertEqual(records_dynamo.read_lines(STATUSES, "2"), [])

    def test_load_all_returns_every_record_of_the_kind_by_id(self):
        records_dynamo.save(LEADS, "b", {"n": 2})
        records_dynamo.save(LEADS, "a", {"n": 1})
        self.assertEqual(records_dynamo.load_all(LEADS), [{"n": 1}, {"n": 2}])

    def test_replace_all_writes_new_and_removes_the_rest(self):
        records_dynamo.save(LEADS, "old", {"n": 0})
        records_dynamo.save(LEADS, "a", {"n": 0})
        records_dynamo.replace_all(LEADS, {"a": {"n": 1}, "b": {"n": 2}})
        self.assertEqual(records_dynamo.list_ids(LEADS), ["a", "b"])
        self.assertEqual(records_dynamo.load(LEADS, "a"), {"n": 1})

    def test_kind_is_folder_name(self):
        records_dynamo.save(Path("/one/leads"), "1", {"a": 1})
        self.assertEqual(records_dynamo.load(Path("/other/leads"), "1"), {"a": 1})


class BackendSwitchTest(unittest.TestCase):
    def test_files_by_default(self):
        from app.db import records, records_files
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertIs(records.backend(), records_files)

    def test_dynamodb_when_set(self):
        from app.db import records
        with mock.patch.dict(os.environ, {"DB_BACKEND": "dynamodb"}):
            self.assertIs(records.backend(), records_dynamo)


if __name__ == "__main__":
    unittest.main()
