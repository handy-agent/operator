# What it does: Test helper — sets a business profile in env (app/business.py reads it) for tests that run
#   agent turns or sends, so they don't depend on .env.
# When it runs: setUp of those tests.
# What calls it: tests that build prompts, tool descriptions or sends (test_estimate, test_estimate_decisions,
#   test_hold_for_operator, test_lead_wrote_meanwhile, test_paused_instruction, test_prompts, test_send_message_price_guard).
import os
import unittest
from unittest import mock

PROFILE = {
    "BUSINESS_OWNER": "Sam",
    "BUSINESS_NAME": "Test Handy Co",
    "BUSINESS_SERVICES": "furniture assembly",
    "BUSINESS_SERVICE_AREA": "Austin",
}


def use(test: unittest.TestCase) -> None:
    patcher = mock.patch.dict(os.environ, PROFILE)
    patcher.start()
    test.addCleanup(patcher.stop)
