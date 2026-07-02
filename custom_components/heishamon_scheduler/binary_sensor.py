"""Binary sensor entities for HeishaMon Scheduler."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import ScheduleCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensor entities."""
    coordinator: ScheduleCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([HeishaMonOnlineSensor(coordinator)])


class HeishaMonOnlineSensor(BinarySensorEntity):
    """Connectivity sensor based on the HeishaMon LWT topic."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: ScheduleCoordinator) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{DOMAIN}_heishamon_online"
        self._attr_name = "HeishaMon Online"

    @property
    def is_on(self) -> bool:
        """Return true if HeishaMon reports online via LWT."""
        return self._coordinator.heishamon_online

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
