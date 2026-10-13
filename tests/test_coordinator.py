"""Regression tests for schedule transitions."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from custom_components.heishamon_scheduler.const import (
    DAYS,
    POWER_COMMAND,
    POWER_FEEDBACK,
)
from custom_components.heishamon_scheduler.coordinator import ScheduleCoordinator


MODE_COMMAND = "SetOperationMode"
MODE_FEEDBACK = "main/Operating_Mode_State"


class FakeEntry:
    """Config entry exposing scheduler options."""

    options: dict[str, Any] = {}

    def __init__(self) -> None:
        self.background_task_name: str | None = None

    def async_create_background_task(
        self,
        _hass,
        target,
        name: str,
    ) -> asyncio.Task:
        """Create and record a config-entry background task."""
        self.background_task_name = name
        return asyncio.create_task(target, name=name)


class FakeStore:
    """In-memory schedule store."""

    def __init__(self, blocks: list[dict]) -> None:
        self.data = {
            "enabled": True,
            "blocks": blocks,
            "baselines": {},
        }
        self.save_count = 0

    @property
    def enabled(self) -> bool:
        return self.data["enabled"]

    def get_blocks(self) -> list[dict]:
        return self.data["blocks"]

    def get_baseline(self, block_id: str) -> Any | None:
        return self.data["baselines"].get(block_id)

    def set_baseline(self, block_id: str, value: Any) -> None:
        self.data["baselines"][block_id] = value

    def pop_baseline(self, block_id: str) -> Any | None:
        return self.data["baselines"].pop(block_id, None)

    async def async_save(self) -> None:
        self.save_count += 1


class FakeHass:
    """Placeholder Home Assistant instance for evaluation-only tests."""


def block(
    block_id: str,
    action: str,
    start: str,
    end: str,
    *,
    value: int | None = None,
    days: list[str] | None = None,
) -> dict:
    """Create a valid schedule block."""
    return {
        "id": block_id,
        "days": list(DAYS if days is None else days),
        "start": start,
        "end": end,
        "action": action,
        "value": value,
        "enabled": True,
    }


def coordinator(blocks: list[dict]) -> tuple[ScheduleCoordinator, FakeStore]:
    """Create a coordinator backed by an in-memory store."""
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())
    store = FakeStore(blocks)
    instance = ScheduleCoordinator(FakeHass(), FakeEntry(), store, "heatpump")
    return instance, store


def queued_commands(instance: ScheduleCoordinator) -> list[tuple[str, Any]]:
    """Drain and return commands without starting the MQTT consumer."""
    commands = []
    while not instance._command_queue.empty():
        command, value = instance._command_queue.get_nowait()
        commands.append((command, value))
        if instance._pending.get(command) == value:
            instance._pending.pop(command)
    return commands


def evaluate(instance: ScheduleCoordinator, now: datetime) -> None:
    """Evaluate on the coordinator's current test event loop."""
    asyncio.get_event_loop().run_until_complete(instance._async_evaluate(now))


def test_cooling_to_dhw_keeps_power_on_and_hands_off_baseline() -> None:
    """A direct mode transition must not restore the old off state."""
    cooling = block("cooling", "cool", "09:30", "13:10", value=18)
    dhw = block("dhw", "dhw", "13:10", "15:20", value=45)
    instance, store = coordinator([cooling, dhw])
    instance._active = {cooling["id"]: cooling}
    instance._applied = {
        cooling["id"]: [
            (MODE_COMMAND, 1),
            ("SetZ1CoolRequestTemperature", 18),
        ]
    }
    store.set_baseline(
        cooling["id"],
        {
            POWER_COMMAND: 0,
            MODE_COMMAND: 2,
            "SetZ1CoolRequestTemperature": 17,
        },
    )
    instance.hp_state = {
        POWER_FEEDBACK: "1",
        MODE_FEEDBACK: "1",
        "main/Z1_Cool_Request_Temp": "18",
        "main/DHW_Target_Temp": "48",
    }

    evaluate(instance, datetime(2026, 7, 14, 13, 10))

    commands = queued_commands(instance)
    assert commands[:3] == [
        (POWER_COMMAND, 1),
        (MODE_COMMAND, 3),
        ("SetDHWTemp", 45),
    ]
    assert (POWER_COMMAND, 0) not in commands
    assert store.get_baseline(dhw["id"])[POWER_COMMAND] == 0
    assert store.get_baseline(dhw["id"])[MODE_COMMAND] == 2


def test_specific_block_end_reapplies_continuing_general_block() -> None:
    """Ending an override must restore the still-active winning block."""
    heating = block("heating", "heat", "09:00", "18:00", value=0)
    dhw = block(
        "dhw",
        "dhw",
        "12:00",
        "13:00",
        value=45,
        days=["tue"],
    )
    instance, store = coordinator([heating, dhw])
    instance._active = {heating["id"]: heating, dhw["id"]: dhw}
    instance._applied = {
        heating["id"]: [(MODE_COMMAND, 0), ("SetZ1HeatRequestTemperature", 0)],
        dhw["id"]: [(MODE_COMMAND, 3), ("SetDHWTemp", 45)],
    }
    store.set_baseline(heating["id"], {MODE_COMMAND: 2})
    store.set_baseline(dhw["id"], {MODE_COMMAND: 0, "SetDHWTemp": 48})
    instance.hp_state = {
        POWER_FEEDBACK: "1",
        MODE_FEEDBACK: "3",
        "main/Z1_Heat_Request_Temp": "0",
        "main/DHW_Target_Temp": "45",
    }

    evaluate(instance, datetime(2026, 7, 14, 13, 1))

    commands = queued_commands(instance)
    assert (MODE_COMMAND, 0) in commands
    assert store.get_baseline(heating["id"])[MODE_COMMAND] == 2


def test_general_block_baseline_moves_to_continuing_specific_block() -> None:
    """The oldest baseline survives when an underlying block ends first."""
    heating = block("heating", "heat", "09:00", "13:00", value=0)
    dhw = block(
        "dhw",
        "dhw",
        "12:00",
        "14:00",
        value=45,
        days=["tue"],
    )
    instance, store = coordinator([heating, dhw])
    instance._active = {heating["id"]: heating, dhw["id"]: dhw}
    instance._applied = {
        heating["id"]: [(MODE_COMMAND, 0), ("SetZ1HeatRequestTemperature", 0)],
        dhw["id"]: [(MODE_COMMAND, 3), ("SetDHWTemp", 45)],
    }
    store.set_baseline(heating["id"], {MODE_COMMAND: 2})
    store.set_baseline(dhw["id"], {MODE_COMMAND: 0, "SetDHWTemp": 48})
    instance.hp_state = {
        POWER_FEEDBACK: "1",
        MODE_FEEDBACK: "3",
        "main/Z1_Heat_Request_Temp": "0",
        "main/DHW_Target_Temp": "45",
    }

    evaluate(instance, datetime(2026, 7, 14, 13, 1))

    assert store.get_baseline(dhw["id"])[MODE_COMMAND] == 2


def test_off_block_restores_actual_previous_power_state() -> None:
    """An off block must not turn on a pump that was already off."""
    off = block("off", "off", "09:00", "10:00")
    instance, store = coordinator([off])
    instance.hp_state = {POWER_FEEDBACK: "0"}

    evaluate(instance, datetime(2026, 7, 14, 9, 0))
    queued_commands(instance)
    instance.hp_state = {POWER_FEEDBACK: "0"}

    evaluate(instance, datetime(2026, 7, 14, 10, 0))

    assert queued_commands(instance) == [(POWER_COMMAND, 0)]
    assert store.get_baseline(off["id"]) is None


def test_feedback_mismatch_is_retried_without_a_block_transition() -> None:
    """A lost MQTT mode command is reasserted on the next evaluation."""
    dhw = block("dhw", "dhw", "12:00", "14:00", value=45)
    instance, _store = coordinator([dhw])
    instance._active = {dhw["id"]: dhw}
    instance._applied = {
        dhw["id"]: [(MODE_COMMAND, 3), ("SetDHWTemp", 45)]
    }
    instance.hp_state = {
        POWER_FEEDBACK: "1",
        MODE_FEEDBACK: "1",
        "main/DHW_Target_Temp": "45",
    }

    evaluate(instance, datetime(2026, 7, 14, 13, 15))

    assert queued_commands(instance) == [(MODE_COMMAND, 3)]


def test_command_consumer_is_a_named_config_entry_background_task() -> None:
    """The permanent consumer must not block Home Assistant startup."""
    instance, _store = coordinator([])

    async def start_and_stop() -> None:
        await instance.async_start()
        assert instance.entry.background_task_name == (
            "HeishaMon Scheduler command consumer"
        )
        assert instance._consumer_task is not None
        assert instance._consumer_task.get_name() == (
            "HeishaMon Scheduler command consumer"
        )
        await instance.async_stop()
        assert instance._consumer_task.done()

    asyncio.get_event_loop().run_until_complete(start_and_stop())


def test_block_ended_during_restart_restores_baseline() -> None:
    """A stored baseline is restored when its block ended while HA was down."""
    dhw = block("dhw", "dhw", "12:00", "14:00", value=45)
    instance, store = coordinator([dhw])
    store.set_baseline(dhw["id"], {MODE_COMMAND: 0, "SetDHWTemp": 48})
    instance.hp_state = {
        POWER_FEEDBACK: "1",
        MODE_FEEDBACK: "3",
        "main/DHW_Target_Temp": "45",
    }

    evaluate(instance, datetime(2026, 7, 14, 14, 30))

    assert queued_commands(instance) == [(MODE_COMMAND, 0), ("SetDHWTemp", 48)]
    assert store.get_baseline(dhw["id"]) is None


def test_block_active_across_restart_keeps_original_baseline() -> None:
    """A block still active after a restart must not recapture its state."""
    dhw = block("dhw", "dhw", "12:00", "14:00", value=45)
    instance, store = coordinator([dhw])
    store.set_baseline(dhw["id"], {MODE_COMMAND: 0, "SetDHWTemp": 48})
    instance.hp_state = {
        POWER_FEEDBACK: "1",
        MODE_FEEDBACK: "3",
        "main/DHW_Target_Temp": "45",
    }

    evaluate(instance, datetime(2026, 7, 14, 13, 0))

    assert store.get_baseline(dhw["id"]) == {MODE_COMMAND: 0, "SetDHWTemp": 48}
    assert (MODE_COMMAND, 0) not in queued_commands(instance)
