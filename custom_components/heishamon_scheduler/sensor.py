"""Sensor entities for HeishaMon Scheduler."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CHANNELS, DOMAIN
from .coordinator import ScheduleCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor entities."""
    coordinator: ScheduleCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []
    for channel_id in coordinator.enabled_channels:
        ch = CHANNELS.get(channel_id)
        if ch:
            entities.append(ScheduleSensor(coordinator, channel_id, ch))

    async_add_entities(entities)


class ScheduleSensor(SensorEntity):
    """Sensor showing the current scheduled value for a channel."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ScheduleCoordinator,
        channel_id: str,
        channel_def: dict,
    ) -> None:
        self._coordinator = coordinator
        self._channel_id = channel_id
        self._channel_def = channel_def

        self._attr_unique_id = f"{DOMAIN}_{channel_id}_scheduled"
        self._attr_name = f"Scheduled {channel_def['name']}"
        self._attr_icon = channel_def.get("icon", "mdi:calendar-clock")
        if channel_def["value_type"] == "number":
            self._attr_native_unit_of_measurement = channel_def.get("unit")

    @property
    def native_value(self):
        """Return the current scheduled value."""
        value = self._coordinator.get_current_scheduled_value(self._channel_id)
        if value is None:
            return None
        ch = self._channel_def
        if ch["value_type"] == "enum":
            return ch["options"].get(value, str(value))
        return value

    @property
    def extra_state_attributes(self):
        """Return extra attributes."""
        attrs = {
            "channel_id": self._channel_id,
            "heishamon_online": self._coordinator.heishamon_online,
        }
        hp_state = self._coordinator.hp_state.get(self._channel_id)
        if hp_state is not None:
            attrs["hp_actual"] = hp_state
        last_sent = self._coordinator.last_sent.get(self._channel_id)
        if last_sent is not None:
            attrs["last_sent"] = last_sent
        next_change = self._coordinator.get_next_change(self._channel_id)
        if next_change:
            attrs["next_change_day"] = next_change["day"]
            attrs["next_change_time"] = next_change["time"]
            attrs["next_change_value"] = next_change["value"]
        return attrs

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
