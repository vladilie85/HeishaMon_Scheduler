"""Minimal Home Assistant stubs for coordinator unit tests."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys
import types


ROOT = Path(__file__).resolve().parents[1]


def _package(name: str, path: Path | None = None) -> types.ModuleType:
    module = types.ModuleType(name)
    module.__path__ = [] if path is None else [str(path)]
    sys.modules[name] = module
    return module


homeassistant = _package("homeassistant")
components = _package("homeassistant.components")
mqtt = types.ModuleType("homeassistant.components.mqtt")


async def _async_subscribe(*_args, **_kwargs):
    return lambda: None


async def _async_publish(*_args, **_kwargs):
    return None


mqtt.async_subscribe = _async_subscribe
mqtt.async_publish = _async_publish
components.mqtt = mqtt
sys.modules["homeassistant.components.mqtt"] = mqtt

config_entries = types.ModuleType("homeassistant.config_entries")
config_entries.ConfigEntry = object
sys.modules["homeassistant.config_entries"] = config_entries

core = types.ModuleType("homeassistant.core")
core.HomeAssistant = object
core.callback = lambda function: function
sys.modules["homeassistant.core"] = core

helpers = _package("homeassistant.helpers")
event = types.ModuleType("homeassistant.helpers.event")
event.async_call_later = lambda *_args, **_kwargs: lambda: None
event.async_track_time_change = lambda *_args, **_kwargs: lambda: None
sys.modules["homeassistant.helpers.event"] = event
helpers.event = event

storage = types.ModuleType("homeassistant.helpers.storage")
storage.Store = object
sys.modules["homeassistant.helpers.storage"] = storage
helpers.storage = storage

util = _package("homeassistant.util")
dt = types.ModuleType("homeassistant.util.dt")
dt.now = datetime.now
sys.modules["homeassistant.util.dt"] = dt
util.dt = dt

custom_components = _package("custom_components", ROOT / "custom_components")
custom_components.heishamon_scheduler = _package(
    "custom_components.heishamon_scheduler",
    ROOT / "custom_components" / "heishamon_scheduler",
)

