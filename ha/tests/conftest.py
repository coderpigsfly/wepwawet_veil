"""Fixtures for the veil_guard_service tests (pytest-homeassistant-custom-component)."""
import os

import custom_components
import pytest

# the test plugin brings its own custom_components package; add this repo's to it
HERE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "custom_components")
if HERE not in custom_components.__path__:
    custom_components.__path__.append(HERE)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let Home Assistant load custom_components/veil_guard_service."""
    yield
