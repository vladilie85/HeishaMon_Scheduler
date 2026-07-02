"""Schedule coordinator for HeishaMon Scheduler."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.components import mqtt
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import (
    async_call_later,
    async_track_time_interval,
)
from homeassistant.util import dt as dt_util

from .const import CHANNELS, MIN_COMMAND_INTERVAL, STARTUP_GRACE
from .storage import ScheduleStore

_LOGGER = logging.getLogger(__name__)


class ScheduleCoordinator:
    """Evaluate schedules and dispatch MQTT commands."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        store: ScheduleStore,
        mqtt_base: str,
        enabled_channels: list[str],
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.store = store
        self.mqtt_base = mqtt_base
        self.enabled_channels = enabled_channels

        # State tracking
        self.last_sent: dict[str, Any] = {}
        self.hp_state: dict[str, Any] = {}
        self.heishamon_online = True

        # Command queue
        self._command_queue: asyncio.Queue = asyncio.Queue()
        self._pending: dict[str, Any] = {}
        self._last_command_time = 0.0
        self._consumer_task: asyncio.Task | None = None
        self._unsub_timer = None
        self._unsub_start = None
        self._unsub_mqtt: list = []

        # Listeners for sensor updates
        self._listeners: list = []

    async def async_start(self) -> None:
        """Start the schedule evaluation loop."""
        # Subscribe to feedback topics
        for channel_id in self.enabled_channels:
            ch = CHANNELS.get(channel_id)
            if ch is None:
                continue
            topic = f"{self.mqtt_base}/{ch['feedback_topic']}"
            unsub = await mqtt.async_subscribe(
                self.hass, topic,
                lambda msg, cid=channel_id: self._on_feedback(cid, msg),
                qos=0,
            )
            self._unsub_mqtt.append(unsub)

        # Subscribe to LWT
        lwt_topic = f"{self.mqtt_base}/LWT"
        unsub = await mqtt.async_subscribe(
            self.hass, lwt_topic, self._on_lwt, qos=0
        )
        self._unsub_mqtt.append(unsub)

        # Start per-minute evaluation
        self._unsub_timer = async_track_time_interval(
            self.hass, self._async_evaluate, timedelta(seconds=60)
        )

        # Start command consumer
        self._consumer_task = self.hass.async_create_task(
            self._async_command_consumer()
        )

        # Delay the initial evaluation so retained feedback/LWT messages
        # can arrive first; otherwise we may command values the heat pump
        # is already running.
        async def _initial_evaluate(_now) -> None:
            self._unsub_start = None
            await self._async_evaluate(dt_util.now())

        self._unsub_start = async_call_later(
            self.hass, STARTUP_GRACE, _initial_evaluate
        )

    async def async_stop(self) -> None:
        """Stop the coordinator."""
        if self._unsub_start:
            self._unsub_start()
            self._unsub_start = None
        if self._unsub_timer:
            self._unsub_timer()
        for unsub in self._unsub_mqtt:
            unsub()
        self._unsub_mqtt.clear()
        if self._consumer_task:
            self._consumer_task.cancel()
            try:
                await self._consumer_task
            except asyncio.CancelledError:
                pass

    async def async_evaluate_now(self) -> None:
        """Force immediate schedule evaluation."""
        await self._async_evaluate(dt_util.now())

    async def _async_evaluate(self, now) -> None:
        """Evaluate all channels against the current schedule."""
        if not self.heishamon_online:
            _LOGGER.debug("HeishaMon offline, skipping evaluation")
            return

        now = dt_util.now()

        # Priority order: operation_mode first, then temperatures
        priority_order = ["operation_mode", "z1_heat_shift", "dhw_temp"]
        channels_to_check = [
            ch for ch in priority_order if ch in self.enabled_channels
        ]
        # Add any remaining channels not in priority list
        for ch in self.enabled_channels:
            if ch not in channels_to_check:
                channels_to_check.append(ch)

        for channel_id in channels_to_check:
            scheduled_value = self.store.get_current_value(channel_id, now)
            if scheduled_value is None:
                continue

            last = self.last_sent.get(channel_id)
            hp_current = self.hp_state.get(channel_id)

            # Only send if different from what we last sent AND different
            # from the actual heat pump state
            if scheduled_value != last:
                if self._pending.get(channel_id) == scheduled_value:
                    # Already queued, waiting for the throttled consumer
                    continue

                if hp_current is not None and self._values_match(
                    channel_id, scheduled_value, hp_current
                ):
                    # HP already at target, update tracking without sending
                    self.last_sent[channel_id] = scheduled_value
                    continue

                _LOGGER.info(
                    "Schedule change for %s: %s -> %s",
                    channel_id, last, scheduled_value,
                )
                await self._queue_command(channel_id, scheduled_value)

        # Notify listeners (sensors)
        self._notify_listeners()

    def _values_match(
        self, channel_id: str, scheduled: Any, actual: Any
    ) -> bool:
        """Check if the scheduled value matches the actual HP state.

        HeishaMon publishes numeric values on all feedback topics. Some
        state topics report more states than the corresponding command
        accepts (e.g. Operating_Mode_State 0-8 vs SetOperationMode 0-6),
        so states are mapped back to command values before comparing.
        """
        ch = CHANNELS.get(channel_id, {})
        state_map = ch.get("state_to_command")
        if state_map is not None:
            try:
                actual = state_map.get(int(float(actual)), actual)
            except (ValueError, TypeError):
                pass
        try:
            return float(actual) == float(scheduled)
        except (ValueError, TypeError):
            return str(actual) == str(scheduled)

    async def _queue_command(self, channel_id: str, value: Any) -> None:
        """Add a command to the throttled queue."""
        self._pending[channel_id] = value
        await self._command_queue.put((channel_id, value))

    async def _async_command_consumer(self) -> None:
        """Drain the command queue with throttling."""
        while True:
            try:
                channel_id, value = await self._command_queue.get()
            except asyncio.CancelledError:
                return

            # Throttle
            now = self.hass.loop.time()
            elapsed = now - self._last_command_time
            if elapsed < MIN_COMMAND_INTERVAL:
                wait = MIN_COMMAND_INTERVAL - elapsed
                _LOGGER.debug("Throttling MQTT command, waiting %.1fs", wait)
                await asyncio.sleep(wait)

            # Send MQTT command
            ch = CHANNELS.get(channel_id)
            if ch is None:
                self._pending.pop(channel_id, None)
                continue

            topic = f"{self.mqtt_base}/commands/{ch['command']}"
            payload = str(value)

            try:
                await mqtt.async_publish(
                    self.hass, topic, payload, qos=0, retain=False
                )
                self.last_sent[channel_id] = value
                self._last_command_time = self.hass.loop.time()
                _LOGGER.info(
                    "Sent MQTT command: %s = %s", topic, payload
                )
            except Exception:
                _LOGGER.exception("Failed to send MQTT command to %s", topic)

            # Clear pending unless a newer value was queued meanwhile
            if self._pending.get(channel_id) == value:
                self._pending.pop(channel_id, None)

            self._command_queue.task_done()

    @callback
    def _on_feedback(self, channel_id: str, msg) -> None:
        """Handle MQTT feedback from the heat pump."""
        self.hp_state[channel_id] = msg.payload
        _LOGGER.debug(
            "HP feedback %s: %s", channel_id, msg.payload
        )

    @callback
    def _on_lwt(self, msg) -> None:
        """Handle HeishaMon LWT (Last Will and Testament)."""
        online = msg.payload.lower() == "online"
        if online != self.heishamon_online:
            _LOGGER.info("HeishaMon status: %s", msg.payload)
            self.heishamon_online = online
            self._notify_listeners()
            if online:
                # Re-evaluate on reconnect
                self.hass.async_create_task(self.async_evaluate_now())

    @property
    def channel_defs(self) -> dict[str, dict]:
        """Enabled channel definitions with per-entry option overrides.

        Z1/Z2 heat request accept either a shift (-5..5) or a direct
        temperature (20..max) depending on the heat pump configuration,
        so the range is user-adjustable.
        """
        defs: dict[str, dict] = {}
        options = self.entry.options
        for channel_id in self.enabled_channels:
            ch = CHANNELS.get(channel_id)
            if ch is None:
                continue
            ch = dict(ch)
            if channel_id in ("z1_heat_shift", "z2_heat_shift"):
                ch["min"] = options.get("heat_request_min", ch["min"])
                ch["max"] = options.get("heat_request_max", ch["max"])
                ch["default"] = max(ch["min"], min(ch["max"], ch["default"]))
            defs[channel_id] = ch
        return defs

    def add_listener(self, listener) -> None:
        """Add a state update listener."""
        self._listeners.append(listener)

    def remove_listener(self, listener) -> None:
        """Remove a state update listener."""
        self._listeners = [l for l in self._listeners if l is not listener]

    @callback
    def _notify_listeners(self) -> None:
        """Notify all listeners of state change."""
        for listener in self._listeners:
            listener()

    def get_current_scheduled_value(self, channel_id: str) -> Any | None:
        """Get the currently scheduled value for a channel."""
        return self.store.get_current_value(channel_id, dt_util.now())

    def get_next_change(self, channel_id: str) -> dict | None:
        """Get the next scheduled change for a channel."""
        now = dt_util.now()
        current_time = now.strftime("%H:%M")
        weekday_idx = now.weekday()

        schedule = self.store.get_schedule("default")
        if not schedule:
            return None

        channel = schedule.get("channels", {}).get(channel_id)
        if not channel or not channel.get("days"):
            return None

        days_data = channel["days"]

        # Look through next 7 days
        from .const import DAYS
        for offset in range(7):
            day_idx = (weekday_idx + offset) % 7
            day_key = DAYS[day_idx]
            entries = days_data.get(day_key, [])

            for entry in entries:
                if offset == 0 and entry["time"] <= current_time:
                    continue
                return {"day": day_key, "time": entry["time"], "value": entry["value"]}

        return None
