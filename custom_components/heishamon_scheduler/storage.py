"""Persistent schedule storage for HeishaMon Scheduler."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DAYS, STORAGE_KEY, STORAGE_VERSION


def _default_schedule() -> dict:
    """Return an empty default schedule."""
    return {
        "version": STORAGE_VERSION,
        "schedules": {
            "default": {
                "name": "Standard",
                "enabled": True,
                "channels": {},
            }
        },
    }


class ScheduleStore:
    """Manage persistent schedule storage."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self.data: dict = {}

    async def async_load(self) -> dict:
        """Load schedules from storage."""
        stored = await self._store.async_load()
        if stored is None:
            self.data = _default_schedule()
        else:
            self.data = stored
        return self.data

    async def async_save(self) -> None:
        """Save schedules to storage."""
        await self._store.async_save(self.data)

    def get_schedule(self, schedule_id: str = "default") -> dict | None:
        """Get a specific schedule."""
        return self.data.get("schedules", {}).get(schedule_id)

    def set_channel_day(
        self,
        schedule_id: str,
        channel_id: str,
        day: str,
        entries: list[dict],
    ) -> None:
        """Set schedule entries for a specific channel and day."""
        schedule = self.data["schedules"].setdefault(schedule_id, {
            "name": schedule_id,
            "enabled": True,
            "channels": {},
        })
        channel = schedule["channels"].setdefault(channel_id, {
            "enabled": True,
            "days": {},
        })
        # Sort entries by time
        channel["days"][day] = sorted(entries, key=lambda e: e["time"])

    def get_current_value(
        self,
        channel_id: str,
        now: datetime,
        schedule_id: str = "default",
    ) -> Any | None:
        """Resolve the effective scheduled value for a channel at a given time.

        Walks backward through the day's entries. If no entry is found before
        the current time, wraps to the previous day's last entry, continuing
        up to 7 days back.
        """
        schedule = self.get_schedule(schedule_id)
        if schedule is None or not schedule.get("enabled", True):
            return None

        channel = schedule.get("channels", {}).get(channel_id)
        if channel is None or not channel.get("enabled", True):
            return None

        days_data = channel.get("days", {})
        if not days_data:
            return None

        current_time = now.strftime("%H:%M")
        weekday_idx = now.weekday()  # 0=Monday

        # Check up to 7 days back; offset 7 wraps to the same weekday of
        # the previous week so times before a day's first entry inherit
        # the schedule instead of resolving to None
        for offset in range(8):
            day_idx = (weekday_idx - offset) % 7
            day_key = DAYS[day_idx]
            entries = days_data.get(day_key, [])

            if not entries:
                continue

            if offset == 0:
                # Current day: find last entry at or before current time
                candidates = [e for e in entries if e["time"] <= current_time]
                if candidates:
                    return candidates[-1]["value"]
            else:
                # Previous days: take the last entry of the day
                return entries[-1]["value"]

        return None
