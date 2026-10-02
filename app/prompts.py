# What it does: Loads the agents' prompt texts from agent/*.md — the one place all prompts live (decided
#   2026-10-02: no prompt text in Python). Fills the business profile ({{BUSINESS_...}}, {{SIGN_OFF}},
#   app/business.py) and the values code passes ({{NAME}}). section() returns one "## name" part of a file
#   (agent/tools.md, agent/turn-notices.md).
# When it runs: Whenever an agent's system prompt, a tool description or a turn notice is built.
# What calls it: app/system_prompt.py, app/agent.py, app/tools.py, app/estimator.py, app/item_lookup.py.
from pathlib import Path

from . import business

# app/prompts.py -> parents[1] is operator/.
AGENT_DIR = Path(__file__).resolve().parents[1] / "agent"


def _fill(text: str, values: dict[str, str]) -> str:
    for name, value in values.items():
        text = text.replace(f"{{{{{name}}}}}", value)
    return business.fill(text)


def text(name: str, **values: str) -> str:
    """The whole agent/<name>.md, filled."""
    return _fill((AGENT_DIR / f"{name}.md").read_text().rstrip("\n"), values)


def section(name: str, heading: str, **values: str) -> str:
    """The body under "## <heading>" in agent/<name>.md, filled."""
    lines = (AGENT_DIR / f"{name}.md").read_text().splitlines()
    try:
        start = lines.index(f"## {heading}") + 1
    except ValueError:
        raise KeyError(f"No section '## {heading}' in agent/{name}.md") from None
    end = next((i for i in range(start, len(lines)) if lines[i].startswith("## ")), len(lines))
    return _fill("\n".join(lines[start:end]).strip("\n"), values)
