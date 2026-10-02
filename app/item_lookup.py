# What it does: Background product lookup. When a lead names an item but sends no link or photos, the
#   agent replies right away and this runs separately: a small web-search-only agent looks for the
#   product page. What it finds goes to the operator only, as a note (see app/webhooks.py
#   make_item_lookup) — never to the lead — so searching never delays a reply.
# When it runs: Started by the agent's look_up_item tool.
# What calls it: app/webhooks.py.
import json
import re

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query

from . import prompts
from .note import Note



async def look_up(description: str) -> dict:
    options = ClaudeAgentOptions(system_prompt=prompts.text("item-lookup"), allowed_tools=["WebSearch"], max_turns=4,
                                 setting_sources=[])  # no filesystem settings, see app/agent.py
    text = ""
    async for message in query(prompt=prompts.section("turn-notices", "lookup-request", DESCRIPTION=description), options=options):
        if isinstance(message, ResultMessage):
            text = message.result or ""
    found = re.search(r"\{.*\}", text, re.DOTALL)
    try:
        result = json.loads(found.group(0)) if found else {}
    except json.JSONDecodeError:
        result = {}
    return {"match": result.get("match"), "candidates": result.get("candidates") or [], "why": result.get("why", "")}


def as_note(description: str, result: dict) -> Note:
    """For the operator only; nothing goes to the lead."""
    lines = [f"Lookup: {description}"]
    if result["match"]:
        lines.append(f"Likely: {result['match']}")
    lines += [f"{c.get('title', '')}: {c.get('url', '')}" for c in result["candidates"] if c.get("url") != result["match"]]
    if not result["match"] and not result["candidates"]:
        lines.append("Nothing found.")
    if result["why"]:
        lines.append(result["why"])
    return Note(source="lookup", lines=lines)
