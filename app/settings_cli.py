# What it does: Shows or changes one customer's settings (app/settings.py) while the system runs.
#   Prints every setting, marking the ones the customer changed from the default.
# When it runs: Whenever a customer's timing/alerting should change (by hand for now; the customer's
#   own settings screen later).
# What calls it: sh/account-settings.sh.
import sys

from . import settings
from .db import accounts


def main(account_id: str, changes: list[str]) -> None:
    if accounts.find(account_id) is None:
        sys.exit(f"No account '{account_id}'. Create it with sh/connect-telegram.sh.")
    try:
        values = settings.update(account_id, dict(c.split("=", 1) for c in changes)) if changes else settings.for_account(account_id)
    except ValueError as error:
        sys.exit(str(error))
    own = accounts.find(account_id).settings
    for key, value in values.items():
        print(f"{key:<26} {value}{'   (changed)' if key in own else ''}")


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()  # DB_BACKEND and DynamoDB settings
    main(sys.argv[1], sys.argv[2:])
