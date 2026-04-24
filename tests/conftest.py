"""
Pytest configuration for eCan.ai tests.

Overrides asyncio mode to 'auto' so all async test functions and fixtures
are automatically recognized without per-method @pytest.mark.asyncio decorators.
"""

import pytest


def pytest_configure(config):
    """Set asyncio mode."""
    config.option.asyncio_mode = "auto"
    config.option.asyncio_default_fixture_loop_scope = "function"


def pytest_collection_modifyitems(config, items):
    """Automatically mark cloud tests to skip unless explicitly requested."""
    for item in items:
        if "cloud" in item.keywords:
            item.add_marker(pytest.mark.skip(reason="Cloud tests skipped by default. Run with --run-cloud to enable."))
