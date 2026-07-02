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

from .const import (
    ACTIONS,
    DAYS,
    MIN_COMMAND_INTERVAL,
    POWER_COMMAND,
    POWER_FEEDBACK,
    STARTUP_GRACE,
)
from .storage import ScheduleStore

_LOGGER = logging.getLogger(__name__)


class ScheduleCoordinator:
    """Evaluate schedule blocks and dispatch MQTT commands.

    A block applies its action while active. When it starts, the current
    heat pump state (from the feedback topic) is captured as a baseline;
    when it ends, that baseline (or the action's fixed restore value) is
    sent back so the pump returns to its own settings/heating curve.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        store: ScheduleStore,
        mqtt_base: str,
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.store = store
        self.mqtt_base = mqtt_base

        # Heat pump state, keyed by feedback topic (without base)
        self.hp_state: dict[str, Any] = {}
        self.heishamon_online = True

        # Active blocks (id -> block) and last applied value per block
        self._active: dict[str, dict] = {}
        self._applied: dict[str, Any] = {}

        # Command queue, deduplicated per MQTT command
        self._command_queue: asyncio.Queue = asyncio.Queue()
        self._pending: dict[str, Any] = {}
        self._last_command_time = 0.0
        self._consumer_task: asyncio.Task | None = None
        self._unsub_timer = None
        self._unsub_start = None
        self._unsub_mqtt: list = []

        # Listeners for entity updates
        self._listeners: list = []

    @property
    def action_defs(self) -> dict[str, dict]:
        """Action definitions with per-entry option overrides applied."""
        defs: dict[str, dict] = {}
        options = self.entry.options
        for action_id, action in ACTIONS.items():
            action = dict(action)
            if action_id == "heat" and "sub" in action:
                sub = dict(action["sub"])
                sub["min"] = options.get("heat_request_min", sub["min"])
                sub["max"] = options.get("heat_request_max", sub["max"])
                sub["default"] = max(
                    sub["min"], min(sub["max"], sub["default"])
                )
                action["sub"] = sub
            defs[action_id] = action
        return defs

    async def async_start(self) -> None:
        """Start the schedule evaluation loop."""
        # Subscribe to all distinct feedback topics (modes and subs)
        topics = {a["feedback_topic"] for a in ACTIONS.values()}
        topics |= {
            a["sub"]["feedback_topic"] for a in ACTIONS.values() if "sub" in a
        }
        for topic in topics:
            unsub = await mqtt.async_subscribe(
                self.hass, f"{self.mqtt_base}/{topic}",
                lambda msg, t=topic: self._on_feedback(t, msg),
                qos=0,
            )
            self._unsub_mqtt.append(unsub)

        # Subscribe to LWT
        unsub = await mqtt.async_subscribe(
            self.hass, f"{self.mqtt_base}/LWT", self._on_lwt, qos=0
        )
        self._unsub_mqtt.append(unsub)

        # Per-minute evaluation
        self._unsub_timer = async_track_time_interval(
            self.hass, self._async_evaluate, timedelta(seconds=60)
        )

        # Command consumer
        self._consumer_task = self.hass.async_create_task(
            self._async_command_consumer()
        )

        # Delay the initial evaluation so retained feedback/LWT messages
        # can arrive first.
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

    @staticmethod
    def _block_active(block: dict, day_key: str, prev_day_key: str, hhmm: str) -> bool:
        """Check whether a block is active at the given local time.

        Blocks with end <= start span midnight: they are active from
        start on a scheduled day until end on the following day.
        """
        if not block.get("enabled", True):
            return False
        start, end = block["start"], block["end"]
        days = block.get("days", [])
        if start < end:
            return day_key in days and start <= hhmm < end
        # Overnight block
        return (day_key in days and hhmm >= start) or (
            prev_day_key in days and hhmm < end
        )

    def _block_commands(self, block: dict) -> list[tuple[str, Any, dict]]:
        """List of (command, value, cmd_def) tuples a block applies.

        Always the mode command; additionally the sub command when the
        block carries a value (e.g. heat shift, DHW target temperature).
        """
        action = self.action_defs.get(block["action"])
        if action is None:
            return []
        commands = [(action["command"], action["apply_value"], action)]
        sub = action.get("sub")
        if sub is not None and block.get("value") is not None:
            commands.append((sub["command"], block["value"], sub))
        return commands

    async def _async_evaluate(self, now) -> None:
        """Evaluate all blocks: apply started, restore ended."""
        if not self.heishamon_online:
            _LOGGER.debug("HeishaMon offline, skipping evaluation")
            return

        now = dt_util.now()
        hhmm = now.strftime("%H:%M")
        day_key = DAYS[now.weekday()]
        prev_day_key = DAYS[(now.weekday() - 1) % 7]

        active: dict[str, dict] = {}
        if self.store.enabled:
            for block in self.store.get_blocks():
                if block["action"] not in ACTIONS:
                    continue
                if self._block_active(block, day_key, prev_day_key, hhmm):
                    active[block["id"]] = block

        # Restore blocks that ended (or were deleted/disabled)
        for block_id, block in list(self._active.items()):
            if block_id not in active:
                await self._end_block(block)

        # Apply new blocks; re-apply if the value was edited while active
        for block_id, block in active.items():
            commands = [(c, v) for c, v, _ in self._block_commands(block)]
            if block_id not in self._active:
                await self._start_block(block)
            elif self._applied.get(block_id) != commands:
                await self._apply_block(block)

        self._active = active
        self._notify_listeners()

    async def _start_block(self, block: dict) -> None:
        """Capture baselines, power on if needed, apply a new block."""
        action = self.action_defs.get(block["action"], {})
        baselines = self.store.get_baseline(block["id"])
        if baselines is None or not isinstance(baselines, dict):
            baselines = {}

        changed = False

        # Mode blocks are pointless while the pump is powered off: turn
        # it on and remember to power it off again when the block ends.
        if action.get("power_on") and POWER_COMMAND not in baselines:
            power_state = self.hp_state.get(POWER_FEEDBACK)
            try:
                power_off = power_state is not None and int(float(power_state)) == 0
            except (ValueError, TypeError):
                power_off = False
            if power_off:
                baselines[POWER_COMMAND] = 0
                changed = True
                _LOGGER.info(
                    "Block %s: heat pump is off, powering on", block["id"]
                )
                await self._queue_command(POWER_COMMAND, 1)

        for command, _value, cmd_def in self._block_commands(block):
            if cmd_def.get("restore") == "baseline" and command not in baselines:
                captured = self._feedback_as_command_value(cmd_def)
                if captured is not None:
                    baselines[command] = captured
                    changed = True
                    _LOGGER.debug(
                        "Captured baseline for block %s: %s = %s",
                        block["id"], command, captured,
                    )
        if changed:
            self.store.set_baseline(block["id"], baselines)
            await self.store.async_save()

        await self._apply_block(block)

    async def _apply_block(self, block: dict) -> None:
        """Send the block's command values (mode + optional sub)."""
        commands = self._block_commands(block)
        for command, value, _cmd_def in commands:
            _LOGGER.info(
                "Block %s starts/changes: %s = %s",
                block["id"], command, value,
            )
            await self._queue_command(command, value)
        self._applied[block["id"]] = [(c, v) for c, v, _ in commands]

    async def _end_block(self, block: dict) -> None:
        """Restore the pre-block state for an ended block."""
        applied = self._applied.pop(block["id"], None)
        action = self.action_defs.get(block["action"])
        if action is None:
            return

        baselines = self.store.pop_baseline(block["id"])
        await self.store.async_save()
        if baselines is not None and not isinstance(baselines, dict):
            # Legacy schema: plain value for the mode command
            baselines = {action["command"]: baselines}
        baselines = baselines or {}
        applied_commands = {c for c, _v in applied} if applied else None

        targets = [action]
        sub = action.get("sub")
        if sub is not None and (
            block.get("value") is not None
            or sub["command"] in baselines
            or (applied_commands and sub["command"] in applied_commands)
        ):
            targets.append(sub)

        for cmd_def in targets:
            command = cmd_def["command"]
            if cmd_def["restore"] == "fixed":
                restore = cmd_def["restore_value"]
            else:
                restore = baselines.get(command)
                if restore is None:
                    restore = cmd_def.get("restore_fallback")
            if restore is None:
                _LOGGER.warning(
                    "Block %s ended but no baseline was captured for %s; "
                    "not sending a restore command",
                    block["id"], command,
                )
                continue
            _LOGGER.info(
                "Block %s ended: restoring %s = %s",
                block["id"], command, restore,
            )
            await self._queue_command(command, restore)

        # If the block powered the pump on, power it off again last
        if action.get("power_on") and POWER_COMMAND in baselines:
            _LOGGER.info(
                "Block %s ended: powering heat pump off again", block["id"]
            )
            await self._queue_command(POWER_COMMAND, baselines[POWER_COMMAND])

    def _feedback_as_command_value(self, action: dict) -> Any | None:
        """Convert the current feedback state into a command value."""
        payload = self.hp_state.get(action["feedback_topic"])
        if payload is None:
            return None
        try:
            value = int(float(payload))
        except (ValueError, TypeError):
            return None
        state_map = action.get("state_to_command")
        if state_map is not None:
            value = state_map.get(value, value)
        return value

    async def _queue_command(self, command: str, value: Any) -> None:
        """Add a command to the throttled queue (deduplicated)."""
        if self._pending.get(command) == value:
            return
        self._pending[command] = value
        await self._command_queue.put((command, value))

    async def _async_command_consumer(self) -> None:
        """Drain the command queue with throttling."""
        while True:
            try:
                command, value = await self._command_queue.get()
            except asyncio.CancelledError:
                return

            # Skip stale entries superseded by a newer value
            if self._pending.get(command) != value:
                self._command_queue.task_done()
                continue

            # Throttle
            now = self.hass.loop.time()
            elapsed = now - self._last_command_time
            if elapsed < MIN_COMMAND_INTERVAL:
                wait = MIN_COMMAND_INTERVAL - elapsed
                _LOGGER.debug("Throttling MQTT command, waiting %.1fs", wait)
                await asyncio.sleep(wait)

            topic = f"{self.mqtt_base}/commands/{command}"
            payload = str(value)

            try:
                await mqtt.async_publish(
                    self.hass, topic, payload, qos=0, retain=False
                )
                self._last_command_time = self.hass.loop.time()
                _LOGGER.info("Sent MQTT command: %s = %s", topic, payload)
            except Exception:
                _LOGGER.exception("Failed to send MQTT command to %s", topic)

            if self._pending.get(command) == value:
                self._pending.pop(command, None)

            self._command_queue.task_done()

    @callback
    def _on_feedback(self, topic: str, msg) -> None:
        """Handle MQTT feedback from the heat pump."""
        self.hp_state[topic] = msg.payload
        _LOGGER.debug("HP feedback %s: %s", topic, msg.payload)

    @callback
    def _on_lwt(self, msg) -> None:
        """Handle HeishaMon LWT (Last Will and Testament)."""
        online = msg.payload.lower() == "online"
        if online != self.heishamon_online:
            _LOGGER.info("HeishaMon status: %s", msg.payload)
            self.heishamon_online = online
            self._notify_listeners()
            if online:
                self.hass.async_create_task(self.async_evaluate_now())

    @property
    def active_blocks(self) -> list[dict]:
        """Currently active blocks (for entities)."""
        return list(self._active.values())

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
