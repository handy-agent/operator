# What it does: FastAPI app for the Operator (handyman lead assistant). Local dev entrypoint.
# When it runs: started locally via sh/run.sh (uvicorn app.main:app --env-file .env).
#   .env is loaded by uvicorn, not here — importing this module (tests) never reads .env.
# What calls it: run directly for local dev.
import asyncio
import json
import logging
import os
import secrets
from collections import defaultdict
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request

from app import operator_input
from app.channels.notifier import Notifier
from app.db import traffic_log
from app.messaging.thumbtack import ThumbtackMessagingClient
from app.note import Note, render_text
from app.prices_api import router as prices_router
from app import settings
from app.reply_timing import ReplyScheduler, delays_from_settings
from app.telegram.channel import TelegramChannel
from app.webhooks import handle_thumbtack_event, make_estimator, make_item_lookup, message_from_event, run_batched_turn


log = logging.getLogger("operator")
# One agent turn at a time per lead: a lead message and the owner's instruction never run together.
_lead_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


async def _run_instruction(negotiation_id: str, text: str) -> Note | None:
    async with _lead_locks[negotiation_id]:
        return await operator_input.run_instruction(negotiation_id, text, ThumbtackMessagingClient())


# Notes go to the lead's account on every configured channel (Telegram now; SMS, app later), and to the log.
telegram = TelegramChannel.from_env(_run_instruction)
notifier = Notifier([telegram] if telegram else [])


def _note(negotiation_id: str, note: Note) -> None:
    log.warning("Note to operator (%s):\n%s", negotiation_id, render_text(note))
    notifier.notify_soon(negotiation_id, note)


async def _reply(negotiation_id: str, texts: list[str]) -> None:
    client = ThumbtackMessagingClient()
    lookup = make_item_lookup(client, lambda note: _note(negotiation_id, note))
    estimate = make_estimator(client, lambda note: _note(negotiation_id, note))
    async with _lead_locks[negotiation_id]:
        note = await run_batched_turn(negotiation_id, texts, client, lookup, estimate)
    if note:
        _note(negotiation_id, note)


# Reply timing per lead, from its customer's settings (app/settings.py). Anything needing the customer's
# decision is held for them instead (hold_for_operator in app/tools.py).
scheduler = ReplyScheduler(_reply, delays_for=lambda negotiation_id: delays_from_settings(settings.for_lead(negotiation_id)))


@asynccontextmanager
async def lifespan(app: FastAPI):
    background = [asyncio.create_task(notifier.run_status_sync())]
    if telegram:
        # Production: Telegram calls POST /webhooks/telegram (TELEGRAM_WEBHOOK_URL = this app's public
        # base URL). Without it (local dev), poll Telegram instead.
        if base_url := os.getenv("TELEGRAM_WEBHOOK_URL"):
            await telegram.api.set_webhook(f"{base_url.rstrip('/')}/webhooks/telegram", os.environ["TELEGRAM_WEBHOOK_SECRET"])
        else:
            background.append(asyncio.create_task(telegram.listen()))
    yield
    for task in background:
        task.cancel()


app = FastAPI(title="Operator", lifespan=lifespan)
app.include_router(prices_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/webhooks/thumbtack")
async def thumbtack_webhook(request: Request) -> dict:
    # Every delivery and our response is saved (app/db/traffic_log.py) as recorded test data.
    body = await request.body()
    logged_request = {"method": "POST", "url": str(request.url), "headers": dict(request.headers),
                      "body": traffic_log.body_value(body)}
    try:
        payload = message_from_event(json.loads(body))
        result = ({"handled": False, "reason": "not a message event"} if payload is None
                  else await handle_thumbtack_event(payload, scheduler=scheduler))
    except Exception as exc:
        traffic_log.save("inbound", logged_request, error=repr(exc))
        raise
    traffic_log.save("inbound", logged_request, {"status": 200, "body": result})
    return result


@app.post("/webhooks/telegram")
async def telegram_webhook(request: Request) -> dict:
    # Only Telegram knows the secret (given in setWebhook); anyone else hitting this URL is refused.
    secret = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
    sent = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not telegram or not secret or not secrets.compare_digest(sent, secret):
        raise HTTPException(status_code=403)
    telegram.handle_soon(await request.json())
    return {"ok": True}
