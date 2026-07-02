"""Switch entities for HeishaMon Scheduler."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
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
    """Set up switch entities."""
    coordinator: ScheduleCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([ScheduleMasterSwitch(coordinator)])


class ScheduleMasterSwitch(SwitchEntity):
    """Master enable/disable switch for the schedule."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator: ScheduleCoordinator) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{DOMAIN}_master_enabled"
        self._attr_name = "Schedule Enabled"

    @property
    def is_on(self) -> bool:
        """Return true if the schedule is enabled."""
        return self._coordinator.store.enabled

    async def async_turn_on(self, **kwargs) -> None:
        """Enable the schedule."""
        self._coordinator.store.set_enabled(True)
        await self._coordinator.store.async_save()
        await self._coordinator.async_evaluate_now()
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        """Disable the schedule (active blocks are restored)."""
        self._coordinator.store.set_enabled(False)
        await self._coordinator.store.async_save()
        await self._coordinator.async_evaluate_now()
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        self._coordinator.add_listener(self._handle_update)

    async def async_will_remove_from_hass(self) -> None:
        self._coordinator.remove_listener(self._handle_update)

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()
