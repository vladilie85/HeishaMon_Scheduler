"""HeishaMon Scheduler - Weekly schedule for Panasonic heat pumps."""

from __future__ import annotations

import logging
from pathlib import Path

import voluptuous as vol

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.components.websocket_api import (
    async_register_command,
    async_response,
    websocket_command,
)

from .const import DAYS, DEFAULT_CHANNELS, DOMAIN, VERSION
from .coordinator import ScheduleCoordinator
from .storage import ScheduleStore

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["binary_sensor", "sensor", "switch"]

CARD_FILENAME = "heishamon-scheduler-card.js"
CARD_URL = f"/{DOMAIN}/{CARD_FILENAME}"


async def _async_register_card(hass: HomeAssistant) -> None:
    """Serve the bundled Lovelace card and load it on every frontend page.

    add_extra_js_url injects the module on all dashboards regardless of
    storage/YAML mode, so no Lovelace resource entry is needed. The card
    guards against double definition in case a manual resource exists too.
    """
    if hass.data.get(f"{DOMAIN}_card_registered"):
        return
    hass.data[f"{DOMAIN}_card_registered"] = True

    card_path = Path(__file__).parent / "www" / CARD_FILENAME
    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL, str(card_path), cache_headers=False)]
    )
    add_extra_js_url(hass, f"{CARD_URL}?v={VERSION}")
    _LOGGER.debug("Registered card frontend module %s (v%s)", CARD_URL, VERSION)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up HeishaMon Scheduler from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    store = ScheduleStore(hass)
    await store.async_load()

    # Options (reconfigurable) take precedence over initial config data
    mqtt_base = entry.options.get(
        "mqtt_base_topic",
        entry.data.get("mqtt_base_topic", "panasonic_heat_pump"),
    )
    enabled_channels = entry.options.get(
        "channels", entry.data.get("channels", DEFAULT_CHANNELS)
    )

    coordinator = ScheduleCoordinator(
        hass, entry, store, mqtt_base, enabled_channels
    )
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Serve the bundled card and register WebSocket commands
    await _async_register_card(hass)
    _register_websocket_commands(hass)

    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Reload when options change
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    # Start the schedule evaluation loop
    await coordinator.async_start()

    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    coordinator: ScheduleCoordinator = hass.data[DOMAIN][entry.entry_id]
    await coordinator.async_stop()

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


def _get_coordinator(hass: HomeAssistant) -> ScheduleCoordinator:
    """Get the first available coordinator."""
    for coordinator in hass.data.get(DOMAIN, {}).values():
        return coordinator
    raise ValueError("No HeishaMon Scheduler instance configured")


def _register_websocket_commands(hass: HomeAssistant) -> None:
    """Register WebSocket API commands."""
    if f"{DOMAIN}_ws_registered" in hass.data:
        return
    hass.data[f"{DOMAIN}_ws_registered"] = True

    @websocket_command({
        vol.Required("type"): f"{DOMAIN}/get_schedule",
        vol.Optional("schedule_id", default="default"): str,
    })
    @async_response
    async def ws_get_schedule(hass, connection, msg):
        """Return the full schedule data."""
        coordinator = _get_coordinator(hass)
        schedule = coordinator.store.get_schedule(msg.get("schedule_id", "default"))
        connection.send_result(msg["id"], {
            "schedule": schedule,
            "channels": coordinator.channel_defs,
        })

    @websocket_command({
        vol.Required("type"): f"{DOMAIN}/set_schedule",
        vol.Required("channel_id"): str,
        vol.Required("day"): vol.In(DAYS),
        vol.Required("entries"): list,
        vol.Optional("schedule_id", default="default"): str,
    })
    @async_response
    async def ws_set_schedule(hass, connection, msg):
        """Update schedule entries for a channel/day."""
        coordinator = _get_coordinator(hass)
        channel_id = msg["channel_id"]
        day = msg["day"]
        entries = msg["entries"]
        schedule_id = msg.get("schedule_id", "default")

        # Validate entries against the effective (option-adjusted) definition
        channel_def = coordinator.channel_defs.get(channel_id)
        if channel_def is None:
            connection.send_error(msg["id"], "invalid_channel", f"Unknown channel: {channel_id}")
            return

        validated = []
        for entry in entries:
            time_str = entry.get("time", "")
            value = entry.get("value")
            if not time_str or value is None:
                continue
            # Validate time format
            parts = time_str.split(":")
            if len(parts) != 2:
                continue
            try:
                h, m = int(parts[0]), int(parts[1])
                if not (0 <= h <= 23 and m in (0, 30)):
                    continue
            except ValueError:
                continue
            # Validate value
            if channel_def["value_type"] == "number":
                try:
                    value = int(value)
                except (ValueError, TypeError):
                    continue
                if not (channel_def["min"] <= value <= channel_def["max"]):
                    continue
            elif channel_def["value_type"] == "enum":
                try:
                    value = int(value)
                except (ValueError, TypeError):
                    continue
                if value not in channel_def["options"]:
                    continue
            validated.append({"time": time_str, "value": value})

        coordinator.store.set_channel_day(schedule_id, channel_id, day, validated)
        await coordinator.store.async_save()

        # Re-evaluate immediately
        await coordinator.async_evaluate_now()

        connection.send_result(msg["id"], {"success": True})

    @websocket_command({
        vol.Required("type"): f"{DOMAIN}/set_enabled",
        vol.Optional("schedule_id", default="default"): str,
        vol.Optional("channel_id"): str,
        vol.Required("enabled"): bool,
    })
    @async_response
    async def ws_set_enabled(hass, connection, msg):
        """Enable or disable a schedule or channel."""
        coordinator = _get_coordinator(hass)
        schedule_id = msg.get("schedule_id", "default")
        channel_id = msg.get("channel_id")
        enabled = msg["enabled"]

        schedule = coordinator.store.get_schedule(schedule_id)
        if schedule is None:
            connection.send_error(msg["id"], "not_found", "Schedule not found")
            return

        if channel_id:
            channel = schedule.get("channels", {}).get(channel_id)
            if channel:
                channel["enabled"] = enabled
        else:
            schedule["enabled"] = enabled

        await coordinator.store.async_save()
        await coordinator.async_evaluate_now()
        connection.send_result(msg["id"], {"success": True})

    async_register_command(hass, ws_get_schedule)
    async_register_command(hass, ws_set_schedule)
    async_register_command(hass, ws_set_enabled)
