"""Pytest configuration for browser-automation tests."""

import pytest
import sys
from pathlib import Path

# Add project root to path for imports
_ROOT = Path(__file__).parent.parent.parent.resolve()
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# Configure asyncio for pytest
# NOTE: pytest_plugins is defined in the root conftest.py


def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers."""
    for item in items:
        # Add browser marker to tests that need real browser
        if "browser" in item.name.lower() or "browser_session" in item.name.lower():
            item.add_marker(pytest.mark.browser)


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers",
        "gui: tests that require GUI environment (skipped by default)",
    )
    config.addinivalue_line(
        "markers",
        "integration: tests that mock external dependencies",
    )
    config.addinivalue_line(
        "markers",
        "unit: pure unit tests without dependencies",
    )
    config.addinivalue_line(
        "markers",
        "browser: tests that require real browser (skipped if browser unavailable)",
    )


@pytest.fixture(scope="session")
def project_root():
    """Return the project root directory."""
    return _ROOT


@pytest.fixture
def reset_app_context():
    """Reset AppContext singleton before each test."""
    try:
        from tests.browser_automation.mock_infrastructure import MockAppContext

        MockAppContext.reset()
        yield
        MockAppContext.reset()
    except ImportError:
        yield
