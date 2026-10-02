# What it does: Builds the main agent's system prompt from agent/main-agent.md, with agent/reply-style.md and
#   agent/disclosure-whitelist.md filled in. The text itself lives only in agent/ (app/prompts.py).
# When it runs: Called once per agent turn.
# What calls it: app/agent.py.
from . import prompts


def build_system_prompt() -> str:
    return prompts.text(
        "main-agent",
        REPLY_STYLE=prompts.text("reply-style"),
        DISCLOSURE_WHITELIST=prompts.text("disclosure-whitelist"),
    )
