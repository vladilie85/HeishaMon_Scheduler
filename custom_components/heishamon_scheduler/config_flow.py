"""Config flow for HeishaMon Scheduler."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv

from .const import CHANNELS, DEFAULT_CHANNELS, DEFAULT_MQTT_BASE, DOMAIN

CHANNEL_OPTIONS = {
    channel_id: ch["name"] for channel_id, ch in CHANNELS.items()
}


class HeishaMonSchedulerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for HeishaMon Scheduler."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step - MQTT configuration."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Ensure only one instance
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title="HeishaMon Scheduler",
                data={
                    "mqtt_base_topic": user_input["mqtt_base_topic"],
                    "channels": user_input.get("channels", DEFAULT_CHANNELS),
                },
            )

        schema = vol.Schema({
            vol.Required(
                "mqtt_base_topic", default=DEFAULT_MQTT_BASE
            ): cv.string,
            vol.Required(
                "channels", default=DEFAULT_CHANNELS
            ): cv.multi_select(CHANNEL_OPTIONS),
        })

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> HeishaMonSchedulerOptionsFlow:
        """Create the options flow."""
        return HeishaMonSchedulerOptionsFlow()


class HeishaMonSchedulerOptionsFlow(OptionsFlow):
    """Handle options for HeishaMon Scheduler."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        entry = self.config_entry
        current_base = entry.options.get(
            "mqtt_base_topic",
            entry.data.get("mqtt_base_topic", DEFAULT_MQTT_BASE),
        )
        current_channels = entry.options.get(
            "channels", entry.data.get("channels", DEFAULT_CHANNELS)
        )
        current_min = entry.options.get("heat_request_min", -5)
        current_max = entry.options.get("heat_request_max", 5)

        schema = vol.Schema({
            vol.Required("mqtt_base_topic", default=current_base): cv.string,
            vol.Required(
                "channels", default=current_channels
            ): cv.multi_select(CHANNEL_OPTIONS),
            # Z1/Z2 heat request: shift mode uses -5..5, direct
            # temperature mode uses 20..max (pump dependent)
            vol.Required(
                "heat_request_min", default=current_min
            ): vol.All(vol.Coerce(int), vol.Range(min=-5, max=60)),
            vol.Required(
                "heat_request_max", default=current_max
            ): vol.All(vol.Coerce(int), vol.Range(min=5, max=75)),
        })

        return self.async_show_form(step_id="init", data_schema=schema)
