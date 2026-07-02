"""Persistent schedule storage for HeishaMon Scheduler."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import STORAGE_KEY, STORAGE_VERSION


def _defaults() -> dict:
    """Return the default (empty) data structure."""
    return {
        "schema": 2,
        "enabled": True,
        "blocks": [],
        "baselines": {},
    }


class ScheduleStore:
    """Manage persistent schedule storage.

    Schema 2 stores a flat list of schedule blocks:
        {id, days: [mon..sun], start: "HH:MM", end: "HH:MM",
         action, value, enabled}
    plus captured baselines per block id used to restore the heat pump
    state when a block ends.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self.data: dict = _defaults()

    async def async_load(self) -> dict:
        """Load schedules from storage."""
        stored = await self._store.async_load()
        if stored is not None:
            # Merge onto defaults so upgrading from schema 1 (channel
            # based) starts with an empty block list without data loss.
            self.data = {**_defaults(), **stored}
        return self.data

    async def async_save(self) -> None:
        """Save schedules to storage."""
        await self._store.async_save(self.data)

    @property
    def enabled(self) -> bool:
        """Return whether the schedule is enabled."""
        return self.data.get("enabled", True)

    def set_enabled(self, enabled: bool) -> None:
        """Enable/disable the whole schedule."""
        self.data["enabled"] = enabled

    def get_blocks(self) -> list[dict]:
        """Return all schedule blocks."""
        return self.data.get("blocks", [])

    def set_blocks(self, blocks: list[dict]) -> None:
        """Replace the block list."""
        self.data["blocks"] = blocks
        # Drop baselines of deleted blocks
        ids = {b["id"] for b in blocks}
        self.data["baselines"] = {
            bid: val for bid, val in self.data.get("baselines", {}).items()
            if bid in ids
        }

    def get_baseline(self, block_id: str) -> Any | None:
        """Return the captured pre-block state for a block."""
        return self.data.get("baselines", {}).get(block_id)

    def set_baseline(self, block_id: str, value: Any) -> None:
        """Store the captured pre-block state for a block."""
        self.data.setdefault("baselines", {})[block_id] = value

    def pop_baseline(self, block_id: str) -> Any | None:
        """Remove and return the captured pre-block state."""
        return self.data.get("baselines", {}).pop(block_id, None)
