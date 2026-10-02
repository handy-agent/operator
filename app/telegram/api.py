# What it does: Thin client for the Telegram Bot API (https://core.telegram.org/bots/api) — only the
#   calls the operator channel needs. Plain HTTPS via httpx, no extra dependency.
# When it runs: Whenever the Telegram channel talks to customers' chats with the product bot.
# What calls it: app/telegram/channel.py, app/connect.py, app/main.py.
import os
from typing import Any

import httpx

# Long-poll wait for getUpdates (local and simulator runs only; production uses the webhook).
POLL_SECONDS = 10


class TelegramError(Exception):
    pass


class TelegramApi:
    def __init__(self, token: str | None = None) -> None:
        token = token or os.environ["TELEGRAM_BOT_TOKEN"]
        self._base = f"https://api.telegram.org/bot{token}"
        self._http = httpx.AsyncClient(timeout=POLL_SECONDS + 20)

    async def call(self, method: str, **params: Any) -> Any:
        params = {k: v for k, v in params.items() if v is not None}
        response = await self._http.post(f"{self._base}/{method}", json=params)
        body = response.json()
        if not body.get("ok") and "message is not modified" in body.get("description", ""):
            return None  # an edit that changes nothing already has the wanted result
        if not body.get("ok"):
            raise TelegramError(f"{method}: {body.get('description', response.status_code)}")
        return body["result"]

    async def get_me(self) -> dict:
        return await self.call("getMe")

    async def set_webhook(self, url: str, secret: str) -> None:
        # Telegram sends `secret` back in the X-Telegram-Bot-Api-Secret-Token header of every call.
        await self.call("setWebhook", url=url, secret_token=secret, allowed_updates=["message", "callback_query"])

    async def delete_webhook(self) -> None:
        await self.call("deleteWebhook")

    async def send_message(
        self,
        chat_id: int,
        text: str,
        thread_id: int | None = None,
        buttons: list[list[dict]] | None = None,
        silent: bool = False,
        html: bool = False,
    ) -> dict:
        return await self.call(
            "sendMessage",
            chat_id=chat_id,
            text=text,
            message_thread_id=thread_id,
            reply_markup={"inline_keyboard": buttons} if buttons else None,
            disable_notification=silent or None,
            parse_mode="HTML" if html else None,
        )

    async def edit_message(self, chat_id: int, message_id: int, text: str, buttons: list[list[dict]] | None) -> None:
        await self.call(
            "editMessageText",
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup={"inline_keyboard": buttons or []},
        )

    async def delete_messages(self, chat_id: int, message_ids: list[int]) -> None:
        await self.call("deleteMessages", chat_id=chat_id, message_ids=message_ids)

    async def pin(self, chat_id: int, message_id: int) -> None:
        await self.call("pinChatMessage", chat_id=chat_id, message_id=message_id, disable_notification=True)

    async def set_buttons(self, chat_id: int, message_id: int, buttons: list[list[dict]] | None) -> None:
        """Replaces a sent message's inline buttons; None removes them."""
        await self.call(
            "editMessageReplyMarkup",
            chat_id=chat_id,
            message_id=message_id,
            reply_markup={"inline_keyboard": buttons or []},
        )

    async def create_topic(self, chat_id: int, name: str) -> int:
        topic = await self.call("createForumTopic", chat_id=chat_id, name=name)
        return topic["message_thread_id"]

    async def rename_topic(self, chat_id: int, thread_id: int, name: str) -> None:
        await self.call("editForumTopic", chat_id=chat_id, message_thread_id=thread_id, name=name)

    async def get_updates(self, offset: int | None) -> list[dict]:
        return await self.call(
            "getUpdates", offset=offset, timeout=POLL_SECONDS, allowed_updates=["message", "callback_query"]
        )

    async def answer_button(self, callback_query_id: str, text: str) -> None:
        await self.call("answerCallbackQuery", callback_query_id=callback_query_id, text=text)

    async def react(self, chat_id: int, message_id: int, emoji: str) -> None:
        await self.call(
            "setMessageReaction",
            chat_id=chat_id,
            message_id=message_id,
            reaction=[{"type": "emoji", "emoji": emoji}],
        )
