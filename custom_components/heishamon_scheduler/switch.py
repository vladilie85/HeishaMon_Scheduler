"""Switch entities for HeishaMon Scheduler."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
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
    """Set up switch entities."""
    coordinator: ScheduleCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [ScheduleMasterSwitch(coordinator)]
    for channel_id in coordinator.enabled_channels:
        ch = CHANNELS.get(channel_id)
        if ch:
            entities.append(ChannelSwitch(coordinator, channel_id, ch))

    async_add_entities(entities)


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
        schedule = self._coordinator.store.get_schedule("default")
        if schedule is None:
            return False
        return schedule.get("enabled", True)

    async def async_turn_on(self, **kwargs) -> None:
        """Enable the schedule."""
        schedule = self._coordinator.store.get_schedule("default")
        if schedule:
            schedule["enabled"] = True
            await self._coordinator.store.async_save()
            await self._coordinator.async_evaluate_now()
            self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        """Disable the schedule."""
        schedule = self._coordinator.store.get_schedule("default")
        if schedule:
            schedule["enabled"] = False
            await self._coordinator.store.async_save()
            self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        self._coordinator.add_listener(self._handle_update)

    async def async_will_remove_from_hass(self) -> None:
        self._coordinator.remove_listener(self._handle_update)

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()


class ChannelSwitch(SwitchEntity):
    """Enable/disable switch for a specific channel."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ScheduleCoordinator,
        channel_id: str,
        channel_def: dict,
    ) -> None:
        self._coordinator = coordinator
        self._channel_id = channel_id
        self._attr_unique_id = f"{DOMAIN}_{channel_id}_enabled"
        self._attr_name = f"{channel_def['name']} Schedule"
        self._attr_icon = channel_def.get("icon", "mdi:calendar-clock")

    @property
    def is_on(self) -> bool:
        """Return true if this channel's schedule is enabled."""
        schedule = self._coordinator.store.get_schedule("default")
        if schedule is None:
            return False
        channel = schedule.get("channels", {}).get(self._channel_id)
        if channel is None:
            return False
        return channel.get("enabled", True)

    async def async_turn_on(self, **kwargs) -> None:
        schedule = self._coordinator.store.get_schedule("default")
        if schedule:
            channel = schedule.get("channels", {}).get(self._channel_id)
            if channel:
                channel["enabled"] = True
                await self._coordinator.store.async_save()
                await self._coordinator.async_evaluate_now()
                self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        schedule = self._coordinator.store.get_schedule("default")
        if schedule:
            channel = schedule.get("channels", {}).get(self._channel_id)
            if channel:
                channel["enabled"] = False
                await self._coordinator.store.async_save()
                self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        self._coordinator.add_listener(self._handle_update)

    async def async_will_remove_from_hass(self) -> None:
        self._coordinator.remove_listener(self._handle_update)

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()
