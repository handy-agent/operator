# What it does: Unit tests for the note to the operator (app/note.py): the lead's message and what was
#   sent come first, then what the owner must do, then system info; the agent's lines are parsed, "none"
#   lines dropped, and its own retelling of the sent text ignored (code has the exact text).
# When it runs: `.venv/bin/python -m unittest discover tests` from operator/.
# What calls it: developer / Claude, by hand.
import unittest

from app.note import Note, from_agent, render_html, render_terminal, render_text

AGENT_TEXT = """Status: waiting on owner (reply held)
Sent: "Great, see you then"
Saved: none
Waiting on owner for: day & time
Comment: Lead hasn't said yes to $110 yet."""


class NoteTest(unittest.TestCase):
    def test_conversation_first_then_action_then_system_info(self):
        note = from_agent("lead", AGENT_TEXT, ["3pm works", "123 Main St"], [])

        self.assertEqual(render_text(note), "\n".join([
            "💬 3pm works",
            "💬 123 Main St",
            "➡️ nothing",
            "✋ waiting on you: day & time",
            "📝 Lead hasn't said yes to $110 yet.",
        ]))

    def test_sent_text_comes_from_code_not_the_agent(self):
        note = from_agent("instruction", AGENT_TEXT, [], ["$110 for Friday 3pm works for me"])

        self.assertEqual(note.sent, ["$110 for Friday 3pm works for me"])
        self.assertNotIn("Great, see you then", render_text(note))

    def test_unknown_agent_lines_are_kept(self):
        note = from_agent("lead", "Something odd happened.", ["hi"], ["Hi! What do you need?"])

        self.assertEqual(note.lines, ["Something odd happened."])

    def test_terminal_is_colored_with_labels(self):
        text = render_terminal(from_agent("lead", "", ["hi"], ["Hello!"]))

        self.assertIn("\033[1;36m     Lead │ hi\033[0m", text)
        self.assertIn("\033[1;32m     Sent │ Hello!\033[0m", text)

    def test_telegram_html_reads_like_the_chat_with_info_folded(self):
        note = from_agent("lead", AGENT_TEXT, ["3pm <works>"], ["Great & thanks"])

        self.assertEqual(render_html(note, "Ann"), "\n\n".join([
            "<b>Ann</b>\n<blockquote>3pm &lt;works&gt;</blockquote>",
            "<b>You</b> · <i>agent</i>\n<blockquote>Great &amp; thanks</blockquote>",
            "<b>✋ Waiting on you: day &amp; time</b>",
            "<i>Lead hasn&#x27;t said yes to $110 yet.</i>",
        ]))

    def test_item_lookup_in_telegram(self):
        note = Note(source="lookup", lines=["Lookup: dresser", "Likely: https://ikea.com/malm"])

        self.assertEqual(render_html(note), "<b>Item lookup</b>\nLookup: dresser\nLikely: https://ikea.com/malm")


if __name__ == "__main__":
    unittest.main()
