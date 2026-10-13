"""Fixtures for tests against a real Home Assistant instance.

Run from the repository root (Python 3.13+):
    pip install -r tests_ha/requirements.txt
    python -m pytest tests_ha -o asyncio_mode=auto
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load the integration from custom_components."""
    yield
