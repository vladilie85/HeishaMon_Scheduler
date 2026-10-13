"""End-to-end tests of the integration in Home Assistant."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_mqtt_message,
    async_fire_time_changed,
)

from custom_components.heishamon_scheduler.const import (
    DOMAIN,
    STARTUP_GRACE,
    STORAGE_KEY,
)

BASE = "panasonic_heat_pump"
# 2026-07-14 is a Tuesday
NOW = datetime(2026, 7, 14, 12, 30)


@pytest.fixture(autouse=True)
def no_throttle():
    """Send queued MQTT commands without the 5 s spacing."""
    with patch(
        "custom_components.heishamon_scheduler.coordinator.MIN_COMMAND_INTERVAL",
        0,
    ):
        yield


@pytest.fixture
def local_now(freezer):
    """Freeze the clock at NOW in Home Assistant's time zone.

    Request it before hass so auth tokens are issued at the frozen time.
    """
    now = NOW.replace(tzinfo=dt_util.get_default_time_zone())
    freezer.move_to(now)
    return now


def command_publishes(mqtt_mock) -> list[tuple[str, str]]:
    """Return (command, payload) for every published scheduler command."""
    prefix = f"{BASE}/commands/"
    return [
        (call.args[0].removeprefix(prefix), call.args[1])
        for call in mqtt_mock.async_publish.call_args_list
        if call.args[0].startswith(prefix)
    ]


async def wait_for_commands(hass, mqtt_mock, count: int) -> list[tuple[str, str]]:
    """Let the background consumer publish until count commands were sent.

    Only zero-delay yields: timed sleeps never end under a frozen clock.
    """
    for _ in range(200):
        await hass.async_block_till_done()
        if len(command_publishes(mqtt_mock)) >= count:
            break
        await asyncio.sleep(0)
    return command_publishes(mqtt_mock)


async def setup_integration(
    hass: HomeAssistant, **feedback: str
) -> MockConfigEntry:
    """Set up the scheduler with HeishaMon online and feedback published.

    Feedback keyword arguments override the default topic payloads. The
    startup grace period is passed, so the initial evaluation has run.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=DOMAIN,
        data={"mqtt_base_topic": BASE},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    payloads = {
        "LWT": "Online",
        "Heatpump_State": "1",
        "Operating_Mode_State": "0",
        "DHW_Target_Temp": "48",
        "Z1_Heat_Request_Temp": "0",
        "Z1_Cool_Request_Temp": "18",
        **feedback,
    }
    for topic, payload in payloads.items():
        if topic != "LWT":
            topic = f"main/{topic}"
        async_fire_mqtt_message(hass, f"{BASE}/{topic}", payload)
    await hass.async_block_till_done()
    async_fire_time_changed(
        hass, dt_util.utcnow() + timedelta(seconds=STARTUP_GRACE + 1)
    )
    await hass.async_block_till_done()
    return entry


def card_block(**overrides) -> dict:
    """A block as the card sends it."""
    data = {
        "id": "new-1",
        "days": ["tue"],
        "start": "12:00",
        "end": "14:00",
        "action": "dhw",
        "value": 45,
        "enabled": True,
    }
    data.update(overrides)
    return data


# --- Config and options flow -------------------------------------------


async def test_config_flow_rejects_wildcard_and_normalizes_topic(
    hass: HomeAssistant, mqtt_mock
) -> None:
    """Wildcards are rejected, whitespace and trailing slashes stripped."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"mqtt_base_topic": "panasonic/#"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"mqtt_base_topic": "invalid_topic"}

    with patch(
        "custom_components.heishamon_scheduler.async_setup_entry",
        return_value=True,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"mqtt_base_topic": " home/heishamon/ "}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {"mqtt_base_topic": "home/heishamon"}


async def test_options_flow_requires_min_below_max(
    hass: HomeAssistant, mqtt_mock
) -> None:
    """A heat request range with min >= max is rejected."""
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=DOMAIN, data={"mqtt_base_topic": BASE}
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "mqtt_base_topic": BASE,
            "heat_request_min": 40,
            "heat_request_max": 30,
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"heat_request_max": "min_not_below_max"}

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "mqtt_base_topic": f"{BASE}/",
            "heat_request_min": 20,
            "heat_request_max": 55,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {
        "mqtt_base_topic": BASE,
        "heat_request_min": 20,
        "heat_request_max": 55,
    }


# --- WebSocket API -----------------------------------------------------


async def test_read_only_user_can_view_but_not_change(
    hass: HomeAssistant,
    mqtt_mock,
    hass_ws_client,
    hass_read_only_access_token,
) -> None:
    """Changing the schedule requires an administrator."""
    await setup_integration(hass)
    client = await hass_ws_client(hass, hass_read_only_access_token)

    await client.send_json_auto_id({"type": f"{DOMAIN}/get_schedule"})
    result = await client.receive_json()
    assert result["success"]
    assert result["result"]["blocks"] == []

    await client.send_json_auto_id(
        {"type": f"{DOMAIN}/set_blocks", "blocks": [card_block()]}
    )
    result = await client.receive_json()
    assert not result["success"]
    assert result["error"]["code"] == "unauthorized"

    await client.send_json_auto_id(
        {"type": f"{DOMAIN}/set_enabled", "enabled": False}
    )
    result = await client.receive_json()
    assert not result["success"]
    assert result["error"]["code"] == "unauthorized"


async def test_set_blocks_validates_and_limits(
    hass: HomeAssistant, mqtt_mock, hass_ws_client
) -> None:
    """Invalid blocks are dropped, days normalized, huge lists rejected."""
    await setup_integration(hass)
    client = await hass_ws_client(hass)

    await client.send_json_auto_id({
        "type": f"{DOMAIN}/set_blocks",
        "blocks": [
            card_block(days=["fri", "tue", "tue"], start="06:00", end="07:00"),
            card_block(start="7:00", end="08:00"),
            card_block(days="tue"),
            "not a block",
        ],
    })
    result = await client.receive_json()
    assert result["success"]
    blocks = result["result"]["blocks"]
    assert len(blocks) == 1
    assert blocks[0]["days"] == ["tue", "fri"]
    assert len(blocks[0]["id"]) == 12

    await client.send_json_auto_id({
        "type": f"{DOMAIN}/set_blocks",
        "blocks": [card_block()] * 201,
    })
    result = await client.receive_json()
    assert not result["success"]
    assert result["error"]["code"] == "invalid_format"


# --- Schedule behaviour over MQTT --------------------------------------


async def test_active_block_sends_commands_over_mqtt(
    local_now, freezer, hass: HomeAssistant, mqtt_mock, hass_ws_client
) -> None:
    """Saving an active block switches the pump; the end restores it."""
    await setup_integration(hass)
    client = await hass_ws_client(hass)

    await client.send_json_auto_id(
        {"type": f"{DOMAIN}/set_blocks", "blocks": [card_block()]}
    )
    assert (await client.receive_json())["success"]

    commands = await wait_for_commands(hass, mqtt_mock, 3)
    assert commands == [
        ("SetHeatpump", "1"),
        ("SetOperationMode", "3"),
        ("SetDHWTemp", "45"),
    ]
    state = hass.states.get(
        er.async_get(hass).async_get_entity_id(
            "sensor", DOMAIN, f"{DOMAIN}_active_blocks"
        )
    )
    assert state.state == "Warmwasser 45°C"

    # Feedback confirms the block; at 14:00 the previous state returns
    async_fire_mqtt_message(hass, f"{BASE}/main/Operating_Mode_State", "3")
    async_fire_mqtt_message(hass, f"{BASE}/main/DHW_Target_Temp", "45")
    mqtt_mock.async_publish.reset_mock()
    end = local_now.replace(hour=14, minute=0)
    freezer.move_to(end)
    async_fire_time_changed(hass, end)

    commands = await wait_for_commands(hass, mqtt_mock, 2)
    assert commands == [("SetOperationMode", "0"), ("SetDHWTemp", "48")]


async def test_block_that_ended_during_restart_is_restored(
    local_now, hass: HomeAssistant, mqtt_mock, hass_storage
) -> None:
    """A baseline left over from before a restart is sent back."""
    hass_storage[STORAGE_KEY] = {
        "version": 1,
        "minor_version": 1,
        "key": STORAGE_KEY,
        "data": {
            "schema": 2,
            "enabled": True,
            "blocks": [{
                "id": "0123456789ab",
                "days": ["tue"],
                "start": "10:00",
                "end": "12:00",
                "action": "dhw",
                "value": 45,
                "enabled": True,
            }],
            "baselines": {
                "0123456789ab": {"SetOperationMode": 0, "SetDHWTemp": 48},
            },
        },
    }
    # The pump is still in the block's state when Home Assistant returns
    await setup_integration(
        hass, Operating_Mode_State="3", DHW_Target_Temp="45"
    )

    commands = await wait_for_commands(hass, mqtt_mock, 2)
    assert commands == [("SetOperationMode", "0"), ("SetDHWTemp", "48")]


async def test_master_switch_state_updates_while_heishamon_offline(
    hass: HomeAssistant, mqtt_mock, hass_ws_client
) -> None:
    """Toggling via the card updates the switch even without HeishaMon."""
    await setup_integration(hass)
    async_fire_mqtt_message(hass, f"{BASE}/LWT", "Offline")
    await hass.async_block_till_done()
    entity_id = er.async_get(hass).async_get_entity_id(
        "switch", DOMAIN, f"{DOMAIN}_master_enabled"
    )
    assert hass.states.get(entity_id).state == "on"

    client = await hass_ws_client(hass)
    await client.send_json_auto_id(
        {"type": f"{DOMAIN}/set_enabled", "enabled": False}
    )
    assert (await client.receive_json())["success"]
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == "off"


async def test_card_is_served(
    hass: HomeAssistant, mqtt_mock, hass_client
) -> None:
    """The bundled Lovelace card is reachable over HTTP."""
    await setup_integration(hass)
    client = await hass_client()
    response = await client.get(f"/{DOMAIN}/heishamon-scheduler-card.js")
    assert response.status == 200
    assert "heishamon-scheduler-card" in await response.text()


async def test_mqtt_callbacks_run_in_event_loop(
    hass: HomeAssistant, mqtt_mock
) -> None:
    """Feedback handlers must not be dispatched to executor threads."""
    from homeassistant.components import mqtt
    from homeassistant.core import HassJobType, get_hassjob_callable_job_type

    handlers = []
    original = mqtt.async_subscribe

    async def record(hass, topic, msg_callback, *args, **kwargs):
        handlers.append((topic, msg_callback))
        return await original(hass, topic, msg_callback, *args, **kwargs)

    with patch(
        "custom_components.heishamon_scheduler.coordinator.mqtt.async_subscribe",
        record,
    ):
        await setup_integration(hass)

    assert len(handlers) == 6
    for topic, handler in handlers:
        assert get_hassjob_callable_job_type(handler) is HassJobType.Callback, topic
