# What it does: Calendar abstraction — checks the owner's availability for scheduling negotiations.
#   Mirrors the messaging/base.py pattern: interface here, platform implementation separate, so
#   swapping calendar providers doesn't touch callers (decided 2026-09-23).
# When it runs: Implemented by app/scheduling/google_calendar.py (not built — needs OAuth setup
#   the owner hasn't done yet). Consumed by app/tools.py's check_availability tool.
# What calls it: app/tools.py.
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class TimeSlot:
    start: str  # ISO 8601
    end: str  # ISO 8601


class CalendarClient(ABC):
    @abstractmethod
    async def free_slots(self, day: str) -> list[TimeSlot]:
        """day is an ISO date (YYYY-MM-DD). Returns the owner's free slots that day."""
        ...
