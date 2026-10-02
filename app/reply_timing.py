# What it does: Human-like reply timing (decided 2026-09-23). Instead of answering each lead message
#   instantly, waits a random delay; if the lead sends more messages meanwhile, the wait restarts
#   (capped), and then the agent answers everything in one turn. A message arriving while a turn is
#   already running is picked up by a follow-up turn right after it. A new lead's first message is
#   answered right away — no pretending on the first reply (decided 2026-09-25).
# When it runs: For every lead message that passed the webhook's gating.
# What calls it: app/webhooks.py (production scheduler), sim/chat.py (simulator, short delays).
import asyncio
import os
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

RunTurn = Callable[[str, list[str]], Awaitable[None]]
# key -> {"delay_min", "delay_max", "max_wait"}: per-lead timing from its customer's settings.
DelaysFor = Callable[[str], dict]


def delays_from_settings(values: dict) -> dict:
    return {
        "delay_min": values["reply_delay_min_seconds"],
        "delay_max": values["reply_delay_max_seconds"],
        "max_wait": values["reply_max_wait_seconds"],
    }


def delays_from_env(prefix: str, default_min: float, default_max: float, default_max_wait: float) -> dict:
    return {
        "delay_min": float(os.getenv(f"{prefix}_DELAY_MIN_SECONDS", default_min)),
        "delay_max": float(os.getenv(f"{prefix}_DELAY_MAX_SECONDS", default_max)),
        "max_wait": float(os.getenv(f"{prefix}_MAX_WAIT_SECONDS", default_max_wait)),
    }


@dataclass
class _LeadState:
    texts: list[str] = field(default_factory=list)
    first_at: float | None = None
    timer: asyncio.Task | None = None
    running: bool = False


class ReplyScheduler:
    def __init__(
        self,
        run_turn: RunTurn,
        delay_min: float = 0,
        delay_max: float = 0,
        max_wait: float = 0,
        delays_for: DelaysFor | None = None,
    ) -> None:
        """Fixed delays, or delays_for(key) to look them up per lead (production: per customer)."""
        self._run_turn = run_turn
        fixed = {"delay_min": delay_min, "delay_max": delay_max, "max_wait": max_wait}
        self._delays_for = delays_for or (lambda key: fixed)
        self._leads: dict[str, _LeadState] = {}

    def add(self, key: str, text: str, immediate: bool = False) -> None:
        """immediate=True answers without the human-like wait (a new lead's first message)."""
        state = self._leads.setdefault(key, _LeadState())
        state.texts.append(text)
        if not state.running:
            self._restart_timer(key, state, immediate)

    def _restart_timer(self, key: str, state: _LeadState, immediate: bool = False) -> None:
        if state.timer is not None:
            state.timer.cancel()
        now = time.monotonic()
        if state.first_at is None:
            state.first_at = now
        d = self._delays_for(key)
        left_before_cap = max(0.0, state.first_at + d["max_wait"] - now)
        delay = 0.0 if immediate else min(random.uniform(d["delay_min"], d["delay_max"]), left_before_cap)
        state.timer = asyncio.create_task(self._fire_after(key, state, delay))

    async def _fire_after(self, key: str, state: _LeadState, delay: float) -> None:
        await asyncio.sleep(delay)
        state.timer = None
        texts, state.texts, state.first_at = state.texts, [], None
        state.running = True
        try:
            await self._run_turn(key, texts)
        finally:
            state.running = False
            if state.texts:
                self._restart_timer(key, state)
