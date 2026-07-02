"""HeishaMon Scheduler - Schedule blocks for Panasonic heat pumps."""

from __future__ import annotations

import logging
import re
import uuid
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

from .const import DAYS, DOMAIN, VERSION
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

    mqtt_base = entry.options.get(
        "mqtt_base_topic",
        entry.data.get("mqtt_base_topic", "panasonic_heat_pump"),
    )

    coordinator = ScheduleCoordinator(hass, entry, store, mqtt_base)
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await _async_register_card(hass)
    _register_websocket_commands(hass)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

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


def _valid_time(value: str) -> bool:
    """Validate HH:MM in 10-minute steps (00:00-24:00)."""
    parts = str(value).split(":")
    if len(parts) != 2:
        return False
    try:
        h, m = int(parts[0]), int(parts[1])
    except ValueError:
        return False
    if h == 24 and m == 0:
        return True
    return 0 <= h <= 23 and 0 <= m <= 59 and m % 10 == 0


def _validate_block(block: dict, action_defs: dict) -> dict | None:
    """Validate and normalize a schedule block; None if invalid."""
    action_id = block.get("action")
    action = action_defs.get(action_id)
    if action is None:
        return None

    days = [d for d in block.get("days", []) if d in DAYS]
    start = block.get("start", "")
    end = block.get("end", "")
    if not days or not _valid_time(start) or not _valid_time(end):
        return None
    if start == end:
        return None

    # Optional sub-setting (heat shift / target temperature); None means
    # "leave the pump's own setting untouched"
    value = block.get("value")
    sub = action.get("sub")
    if value is None or sub is None:
        value = None
    elif sub["value_type"] == "number":
        try:
            value = int(value)
        except (ValueError, TypeError):
            value = sub["default"]
        value = max(sub["min"], min(sub["max"], value))
    elif sub["value_type"] == "enum":
        try:
            value = int(value)
        except (ValueError, TypeError):
            value = sub["default"]
        if value not in sub["options"]:
            value = sub["default"]

    # Only accept server-assigned ids (12 hex chars); anything else is a
    # temporary card id and gets a fresh unique one. Prevents duplicate
    # ids like "new-1" from surviving a save.
    block_id = block.get("id")
    if not isinstance(block_id, str) or not re.fullmatch(r"[0-9a-f]{12}", block_id):
        block_id = uuid.uuid4().hex[:12]
    return {
        "id": block_id,
        "days": days,
        "start": start,
        "end": end,
        "action": action_id,
        "value": value,
        "enabled": bool(block.get("enabled", True)),
    }


def _register_websocket_commands(hass: HomeAssistant) -> None:
    """Register WebSocket API commands."""
    if f"{DOMAIN}_ws_registered" in hass.data:
        return
    hass.data[f"{DOMAIN}_ws_registered"] = True

    @websocket_command({
        vol.Required("type"): f"{DOMAIN}/get_schedule",
    })
    @async_response
    async def ws_get_schedule(hass, connection, msg):
        """Return blocks, action definitions and the enabled flag."""
        coordinator = _get_coordinator(hass)
        connection.send_result(msg["id"], {
            "enabled": coordinator.store.enabled,
            "blocks": coordinator.store.get_blocks(),
            "actions": coordinator.action_defs,
            "active": [b["id"] for b in coordinator.active_blocks],
        })

    @websocket_command({
        vol.Required("type"): f"{DOMAIN}/set_blocks",
        vol.Required("blocks"): list,
    })
    @async_response
    async def ws_set_blocks(hass, connection, msg):
        """Replace the schedule block list."""
        coordinator = _get_coordinator(hass)
        action_defs = coordinator.action_defs

        validated = []
        seen_ids: set[str] = set()
        for block in msg["blocks"]:
            if not isinstance(block, dict):
                continue
            valid = _validate_block(block, action_defs)
            if valid is None:
                continue
            # Deduplicate ids defensively (e.g. legacy duplicate data)
            if valid["id"] in seen_ids:
                valid["id"] = uuid.uuid4().hex[:12]
            seen_ids.add(valid["id"])
            validated.append(valid)

        coordinator.store.set_blocks(validated)
        await coordinator.store.async_save()
        await coordinator.async_evaluate_now()

        connection.send_result(msg["id"], {"blocks": validated})

    @websocket_command({
        vol.Required("type"): f"{DOMAIN}/set_enabled",
        vol.Required("enabled"): bool,
    })
    @async_response
    async def ws_set_enabled(hass, connection, msg):
        """Enable or disable the whole schedule."""
        coordinator = _get_coordinator(hass)
        coordinator.store.set_enabled(msg["enabled"])
        await coordinator.store.async_save()
        await coordinator.async_evaluate_now()
        connection.send_result(msg["id"], {"success": True})

    async_register_command(hass, ws_get_schedule)
    async_register_command(hass, ws_set_blocks)
    async_register_command(hass, ws_set_enabled)
