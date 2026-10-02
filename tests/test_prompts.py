# What it does: Unit tests for the prompt loader (app/prompts.py): every prompt the code asks for exists in
#   agent/*.md, values get filled, and no prompt text is left in Python's agent-facing modules.
# When it runs: `.venv/bin/python -m unittest discover tests` from operator/.
# What calls it: developer / Claude, by hand.
import re
import unittest
from pathlib import Path

from app import prompts
from tests import business_env

APP = Path(__file__).resolve().parents[1] / "app"


class PromptsTest(unittest.TestCase):
    def setUp(self):
        business_env.use(self)

    def test_every_prompt_the_code_uses_exists(self):
        code = "\n".join(p.read_text() for p in APP.rglob("*.py"))
        for name, heading in re.findall(r'prompts\.section\("([\w-]+)", "([\w-]+)"', code):
            with self.subTest(f"{name}#{heading}"):
                prompts.section(name, heading, **{k: "x" for k in ("TEXT",)})
        for name in re.findall(r'prompts\.text\("([\w-]+)"', code):
            with self.subTest(name):
                self.assertTrue((prompts.AGENT_DIR / f"{name}.md").exists())

    def test_section_fills_values_and_stops_at_next_heading(self):
        text = prompts.section("turn-notices", "lead-messages", TEXT="hi")
        self.assertEqual(text, "New lead message(s):\nhi")

    def test_unknown_section_fails(self):
        with self.assertRaises(KeyError):
            prompts.section("turn-notices", "nope")


if __name__ == "__main__":
    unittest.main()
