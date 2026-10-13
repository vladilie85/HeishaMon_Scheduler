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

from .const import DEFAULT_MQTT_BASE, DOMAIN
from .validation import normalize_mqtt_base_topic, valid_mqtt_base_topic


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

            base = normalize_mqtt_base_topic(user_input["mqtt_base_topic"])
            if valid_mqtt_base_topic(base):
                return self.async_create_entry(
                    title="HeishaMon Scheduler",
                    data={"mqtt_base_topic": base},
                )
            errors["mqtt_base_topic"] = "invalid_topic"

        schema = vol.Schema({
            vol.Required(
                "mqtt_base_topic", default=DEFAULT_MQTT_BASE
            ): cv.string,
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
        errors: dict[str, str] = {}
        if user_input is not None:
            base = normalize_mqtt_base_topic(user_input["mqtt_base_topic"])
            if not valid_mqtt_base_topic(base):
                errors["mqtt_base_topic"] = "invalid_topic"
            elif user_input["heat_request_min"] >= user_input["heat_request_max"]:
                errors["heat_request_max"] = "min_not_below_max"
            else:
                return self.async_create_entry(
                    title="", data={**user_input, "mqtt_base_topic": base}
                )

        entry = self.config_entry
        current_base = entry.options.get(
            "mqtt_base_topic",
            entry.data.get("mqtt_base_topic", DEFAULT_MQTT_BASE),
        )
        current_min = entry.options.get("heat_request_min", -5)
        current_max = entry.options.get("heat_request_max", 5)

        schema = vol.Schema({
            vol.Required("mqtt_base_topic", default=current_base): cv.string,
            # Z1 heat request: shift mode uses -5..5, direct temperature
            # mode uses 20..max (pump dependent)
            vol.Required(
                "heat_request_min", default=current_min
            ): vol.All(vol.Coerce(int), vol.Range(min=-5, max=60)),
            vol.Required(
                "heat_request_max", default=current_max
            ): vol.All(vol.Coerce(int), vol.Range(min=5, max=75)),
        })

        return self.async_show_form(
            step_id="init", data_schema=schema, errors=errors
        )
