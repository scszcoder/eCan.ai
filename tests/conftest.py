"""
Pytest configuration for eCan.ai tests.

Overrides asyncio mode to 'auto' so all async test functions and fixtures
are automatically recognized without per-method @pytest.mark.asyncio decorators.
"""

import pytest


def pytest_configure(config):
    """Override asyncio_mode to 'auto' for this test directory."""
    config.option.asyncio_mode = "auto"
    # Suppress deprecation warning and align fixture loop scope with test scope
    config.option.asyncio_default_fixture_loop_scope = "function"
