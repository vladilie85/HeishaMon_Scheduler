"""Tests for schedule input validation."""

from __future__ import annotations

from custom_components.heishamon_scheduler.const import ACTIONS
from custom_components.heishamon_scheduler.validation import (
    normalize_mqtt_base_topic,
    valid_mqtt_base_topic,
    valid_time,
    validate_block,
)


def raw_block(**overrides) -> dict:
    """Create a block as the card would send it."""
    data = {
        "id": "new-1",
        "days": ["mon", "tue"],
        "start": "07:00",
        "end": "12:00",
        "action": "heat",
        "value": None,
        "enabled": True,
    }
    data.update(overrides)
    return data


def test_valid_time_requires_zero_padded_ten_minute_steps() -> None:
    """Times are compared as strings and must have a canonical format."""
    for value in ("00:00", "07:10", "23:50", "24:00"):
        assert valid_time(value)
    for value in ("7:00", "+7:00", " 7:00", "07:0", "07:05", "24:10", "25:00", 700, None):
        assert not valid_time(value)


def test_validate_block_normalizes_days() -> None:
    """Duplicate days must not raise a block's priority."""
    result = validate_block(raw_block(days=["tue", "mon", "mon", "xyz"]), ACTIONS)
    assert result["days"] == ["mon", "tue"]


def test_validate_block_rejects_malformed_input() -> None:
    """Malformed blocks are dropped instead of raising."""
    assert validate_block(raw_block(days=7), ACTIONS) is None
    assert validate_block(raw_block(days="mon"), ACTIONS) is None
    assert validate_block(raw_block(action=["heat"]), ACTIONS) is None
    assert validate_block(raw_block(start="7:00"), ACTIONS) is None
    assert validate_block(raw_block(end="07:00"), ACTIONS) is None


def test_validate_block_clamps_values() -> None:
    """Sub values are clamped to the action range."""
    assert validate_block(raw_block(value=99), ACTIONS)["value"] == 5
    assert validate_block(raw_block(value=float("inf")), ACTIONS)["value"] == 0
    assert validate_block(raw_block(enabled="false"), ACTIONS)["enabled"] is True
    assert validate_block(raw_block(enabled=False), ACTIONS)["enabled"] is False


def test_mqtt_base_topic_validation() -> None:
    """Wildcards and empty topics would break subscriptions and commands."""
    assert normalize_mqtt_base_topic(" panasonic_heat_pump/ ") == "panasonic_heat_pump"
    assert valid_mqtt_base_topic("home/panasonic_heat_pump")
    for value in ("", "/panasonic", "panasonic/#", "panasonic/+/x"):
        assert not valid_mqtt_base_topic(value)
