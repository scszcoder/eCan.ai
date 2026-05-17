"""Browser automation testing package.

This package provides testing infrastructure for browser-automation nodes
in the eCan.ai skill framework.

Architecture
------------
The testing is organized into three layers:

1. **Unit Tests** (test_config.py)
   - Pure parsing logic without dependencies
   - NodeConfig parsing
   - Scope key resolution
   - Helper functions

2. **Integration Tests** (test_runner_integration.py)
   - Mocked browser sessions and mainwin
   - Runner logic and hook mechanisms
   - Session management

3. **E2E Tests** (test_e2e.py)
   - Requires full GUI environment
   - Real browser automation
   - Full skill workflow testing

Usage
-----
```bash
# Run unit tests only (no GUI required)
pytest tests/browser_automation/test_config.py -v

# Run integration tests (no GUI required)
pytest tests/browser_automation/test_runner_integration.py -v

# Run E2E tests (requires GUI)
pytest tests/browser_automation/test_e2e.py -v --gui

# Run all tests
pytest tests/browser_automation/ -v
```

Fixtures
--------
- `mock_infrastructure.py`: Mock implementations of AppContext, MainWindow, etc.
- `conftest.py`: Shared pytest fixtures and configuration
"""

from tests.browser_automation.mock_infrastructure import (
    MockAppContext,
    MockMainWindow,
    MockBrowserSession,
    MockUnifiedBrowserManager,
    AppContextTestManager,
    create_mock_browser_node_config,
    create_mock_state,
)

__all__ = [
    "MockAppContext",
    "MockMainWindow",
    "MockBrowserSession",
    "MockUnifiedBrowserManager",
    "AppContextTestManager",
    "create_mock_browser_node_config",
    "create_mock_state",
]
