# What it does: Thumbtack implementation of MessagingClient, using the Partner Messages API
#   (POST/GET /api/v4/negotiations/{negotiationID}/messages). See ../../thumbtack.md. Every call and
#   its response is saved to the traffic log (app/db/traffic_log.py).
# When it runs: Used whenever the active lead's platform is Thumbtack.
# What calls it: app/tools.py.
#
# THUMBTACK_API_BASE_URL: https://api.thumbtack.com (production) or https://staging-api.thumbtack.com
# (staging), per the Environments doc — see REQUIREMENTS.md. THUMBTACK_API_TOKEN: OAuth access token;
# the OAuth flow that gets it isn't built yet.
import os

import httpx

from ..db import sent_messages, traffic_log
from .base import Message, MessagingClient


class ThumbtackMessagingClient(MessagingClient):
    def __init__(self, base_url: str | None = None, api_token: str | None = None) -> None:
        self.base_url = base_url or os.environ["THUMBTACK_API_BASE_URL"]
        self.api_token = api_token or os.environ["THUMBTACK_API_TOKEN"]

    def _headers(self) -> dict[str, str]:
        return {"authorization": f"Bearer {self.api_token}"}

    async def _call(self, method: str, url: str, json_body: dict | None = None) -> httpx.Response:
        """One API call, saved to the traffic log (app/db/traffic_log.py) whatever the outcome."""
        headers = self._headers()
        logged_request = {"method": method, "url": url, "headers": headers, "body": json_body}
        try:
            async with httpx.AsyncClient() as client:
                response = await client.request(method, url, headers=headers, json=json_body)
        except httpx.HTTPError as exc:
            traffic_log.save("outbound", logged_request, error=repr(exc))
            raise
        traffic_log.save("outbound", logged_request, {
            "status": response.status_code,
            "headers": dict(response.headers),
            "body": traffic_log.body_value(response.content),
        })
        response.raise_for_status()
        return response

    async def send_message(self, session_id: str, text: str) -> None:
        url = f"{self.base_url}/api/v4/negotiations/{session_id}/messages"
        await self._call("POST", url, {"text": text})
        sent_messages.record(session_id, text)

    async def get_messages(self, session_id: str) -> list[Message]:
        url = f"{self.base_url}/api/v4/negotiations/{session_id}/messages"
        payload = (await self._call("GET", url)).json()
        sent_by_agent = sent_messages.texts(session_id)
        return [
            Message(
                sender=_sender(item, sent_by_agent),
                text=item["text"],
                sent_at=item["sentAt"],
                message_id=item.get("messageID"),
            )
            for item in payload.get("data", [])
        ]


def _sender(item: dict, sent_by_agent: set[str]) -> str:
    # Thumbtack labels all pro-side messages alike; anything the agent didn't send is the operator's.
    if item.get("from") == "Customer":
        return "lead"
    return "agent" if item["text"] in sent_by_agent else "operator"
