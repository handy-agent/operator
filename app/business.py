# What it does: The customer's business profile, from env (.env locally, the deploy per stage):
#   BUSINESS_OWNER, BUSINESS_NAME, BUSINESS_SERVICES, BUSINESS_SERVICE_AREA. Fills the {{...}} placeholders
#   in the agent's prompt files (agent/*.md) and gives the sign-off. Kept out of code so the product
#   carries no customer's details (decided 2026-10-02). A missing value raises: never a blank to a lead.
# When it runs: On every agent turn (prompt) and every send (sign-off check).
# What calls it: app/system_prompt.py, app/tools.py.
import os

FIELDS = ("BUSINESS_OWNER", "BUSINESS_NAME", "BUSINESS_SERVICES", "BUSINESS_SERVICE_AREA")


def profile() -> dict[str, str]:
    values = {name: os.environ.get(name, "").strip() for name in FIELDS}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise RuntimeError(f"Business profile missing in env: {', '.join(missing)} (see .env.example)")
    return values


def sign_off() -> str:
    values = profile()
    return f"{values['BUSINESS_OWNER']}, {values['BUSINESS_NAME']}"


def fill(text: str) -> str:
    """Replaces {{BUSINESS_...}} and {{SIGN_OFF}} placeholders in a prompt file."""
    if "{{BUSINESS_" not in text and "{{SIGN_OFF}}" not in text:
        return text
    for name, value in {**profile(), "SIGN_OFF": sign_off()}.items():
        text = text.replace(f"{{{{{name}}}}}", value)
    return text
