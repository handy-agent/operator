# What it does: Unit tests for the business profile from env (app/business.py): it fills the agent's
#   prompt files, gives the sign-off, and a missing value fails loudly instead of reaching a lead blank.
# When it runs: `.venv/bin/python -m unittest discover tests` from operator/.
# What calls it: developer / Claude, by hand.
import os
import unittest
from unittest import mock

from app import business, system_prompt

PROFILE = {
    "BUSINESS_OWNER": "Sam",
    "BUSINESS_NAME": "Test Handy Co",
    "BUSINESS_SERVICES": "shelf mounting",
    "BUSINESS_SERVICE_AREA": "Testville",
}


class BusinessTest(unittest.TestCase):
    def test_prompt_uses_the_profile(self):
        with mock.patch.dict(os.environ, PROFILE):
            prompt = system_prompt.build_system_prompt()
        self.assertIn('Sign "Sam, Test Handy Co"', prompt)
        self.assertIn("shelf mounting", prompt)
        self.assertIn("Testville", prompt)
        self.assertNotIn("{{", prompt)

    def test_sign_off(self):
        with mock.patch.dict(os.environ, PROFILE):
            self.assertEqual(business.sign_off(), "Sam, Test Handy Co")

    def test_missing_value_fails(self):
        with mock.patch.dict(os.environ, {**PROFILE, "BUSINESS_NAME": ""}):
            with self.assertRaises(RuntimeError):
                business.profile()


if __name__ == "__main__":
    unittest.main()
