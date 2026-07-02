"""Sensor entities for HeishaMon Scheduler."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ACTIONS, DOMAIN
from .coordinator import ScheduleCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor entities."""
    coordinator: ScheduleCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([ActiveBlocksSensor(coordinator)])


class ActiveBlocksSensor(SensorEntity):
    """Sensor showing which schedule actions are currently active."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator: ScheduleCoordinator) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{DOMAIN}_active_blocks"
        self._attr_name = "Active Actions"

    @property
    def native_value(self) -> str:
        """Return the active action names, or 'idle'."""
        blocks = self._coordinator.active_blocks
        if not blocks:
            return "idle"
        names = []
        for block in blocks:
            action = ACTIONS.get(block["action"], {})
            name = action.get("name", block["action"])
            sub = action.get("sub")
            if sub is not None and block.get("value") is not None:
                name = f"{name} {block['value']}{sub.get('unit', '')}"
            names.append(name)
        return ", ".join(names)

    @property
    def extra_state_attributes(self):
        """Return extra attributes."""
        c = self._coordinator
        return {
            "heishamon_online": c.heishamon_online,
            "active_blocks": [
                {
                    "id": b["id"],
                    "action": b["action"],
                    "value": b.get("value"),
                    "start": b["start"],
                    "end": b["end"],
                }
                for b in c.active_blocks
            ],
            # Diagnostics: what the scheduler actually did/knows
            "last_commands": list(reversed(c.command_log)),
            "pending_commands": dict(c._pending),
            "heat_pump_feedback": dict(c.hp_state),
        }

    async def async_added_to_hass(self) -> None:
        """Register listener."""
        self._coordinator.add_listener(self._handle_update)

    async def async_will_remove_from_hass(self) -> None:
        """Remove listener."""
        self._coordinator.remove_listener(self._handle_update)

    @callback
    def _handle_update(self) -> None:
        """Handle coordinator state update."""
        self.async_write_ha_state()
