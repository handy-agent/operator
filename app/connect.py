# What it does: Emulates onboarding a customer (a pro like the owner): creates their account if needed and
#   prints a one-time connect link for a channel. Opening the link ties that person's channel to the
#   account. Telegram only for now; SMS and the app get their own connect step later.
# When it runs: When a customer is connected (by hand for now; the product's onboarding later).
# What calls it: sh/connect-telegram.sh.
import asyncio
import sys

from dotenv import load_dotenv

from .db import accounts, channel_links
from .telegram.api import TelegramApi


async def connect_telegram(account_id: str, name: str) -> None:
    account = accounts.find_or_create(account_id, name)
    me = await TelegramApi().get_me()
    if not me.get("has_topics_enabled"):
        print("Warning: topics are off for this bot, so it can't make one topic per lead.\n"
              "Turn on topics (threaded mode) for the bot in @BotFather first.\n")
    code = channel_links.new_connect_code(account.account_id, "telegram")
    print(f"Account: {account.name} ({account.account_id})")
    print(f"Connect link (one-time, {int(channel_links.CODE_TTL.total_seconds() // 3600)}h): "
          f"https://t.me/{me['username']}?start={code}")


if __name__ == "__main__":
    load_dotenv()
    asyncio.run(connect_telegram(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else sys.argv[1]))
