"""Input validation for HeishaMon Scheduler."""

from __future__ import annotations

import re
import uuid

from .const import DAYS

# Upper bound for the block list sent by the card. Far above any real
# schedule, but keeps a client from flooding storage and evaluation.
MAX_BLOCKS = 200

# Zero-padded HH:MM in 10-minute steps, or the end-of-day marker 24:00.
# Blocks are compared as strings, so "7:00" or "+7:00" must be rejected.
_TIME_RE = re.compile(r"(?:[01]\d|2[0-3]):[0-5]0|24:00")

_BLOCK_ID_RE = re.compile(r"[0-9a-f]{12}")


def valid_time(value) -> bool:
    """Validate HH:MM in 10-minute steps (00:00-24:00)."""
    return isinstance(value, str) and _TIME_RE.fullmatch(value) is not None


def valid_mqtt_base_topic(value: str) -> bool:
    """Validate a base topic that commands and subscriptions are built on."""
    return (
        bool(value)
        and not value.startswith("/")
        and "+" not in value
        and "#" not in value
        and "\0" not in value
    )


def normalize_mqtt_base_topic(value) -> str:
    """Strip whitespace and trailing separators from a base topic."""
    return str(value).strip().rstrip("/")


def validate_block(block: dict, action_defs: dict) -> dict | None:
    """Validate and normalize a schedule block; None if invalid."""
    action_id = block.get("action")
    if not isinstance(action_id, str):
        return None
    action = action_defs.get(action_id)
    if action is None:
        return None

    raw_days = block.get("days")
    if not isinstance(raw_days, list):
        return None
    # Canonical order without duplicates: the day count decides which
    # overlapping block wins, so ["mon", "mon"] must not count twice.
    days = [d for d in DAYS if d in raw_days]
    start = block.get("start")
    end = block.get("end")
    if not days or not valid_time(start) or not valid_time(end):
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
        except (ValueError, TypeError, OverflowError):
            value = sub["default"]
        value = max(sub["min"], min(sub["max"], value))
    elif sub["value_type"] == "enum":
        try:
            value = int(value)
        except (ValueError, TypeError, OverflowError):
            value = sub["default"]
        if value not in sub["options"]:
            value = sub["default"]

    # Only accept server-assigned ids (12 hex chars); anything else is a
    # temporary card id and gets a fresh unique one. Prevents duplicate
    # ids like "new-1" from surviving a save.
    block_id = block.get("id")
    if not isinstance(block_id, str) or not _BLOCK_ID_RE.fullmatch(block_id):
        block_id = uuid.uuid4().hex[:12]

    enabled = block.get("enabled", True)
    return {
        "id": block_id,
        "days": days,
        "start": start,
        "end": end,
        "action": action_id,
        "value": value,
        "enabled": enabled if isinstance(enabled, bool) else True,
    }
