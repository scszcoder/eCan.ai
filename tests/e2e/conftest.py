"""E2E Test Fixtures - Shared fixtures for E2E tests.

This module provides pytest fixtures for common E2E test scenarios.
"""

import asyncio
import os
from typing import Any, AsyncGenerator, Dict

import pytest

from tests.e2e_framework import (
    BrowserLauncher,
    BrowserType,
    CDPConnector,
    CDPPage,
    E2ETestContext,
)


# ============================================================================
# Configuration
# ============================================================================

def get_config() -> Dict[str, Any]:
    """Get test configuration from environment or defaults."""
    return {
        "base_url": os.getenv("E2E_BASE_URL", "http://localhost:3000"),
        "cdp_port": int(os.getenv("E2E_CDP_PORT", "9222")),
        "headless": os.getenv("E2E_HEADLESS", "true").lower() == "true",
        "browser": os.getenv("E2E_BROWSER", "chrome").lower(),
        "timeout": int(os.getenv("E2E_TIMEOUT", "30000")),
    }


# ============================================================================
# Browser Fixtures
# ============================================================================

@pytest.fixture(scope="session")
def browser_config() -> Dict[str, Any]:
    """Session-scoped browser configuration."""
    return get_config()


@pytest.fixture(scope="session")
def browser_type() -> BrowserType:
    """Get browser type from config."""
    config = get_config()
    browser = config["browser"]

    if browser == "chrome":
        return BrowserType.CHROME
    elif browser == "firefox":
        return BrowserType.FIREFOX
    elif browser == "edge":
        return BrowserType.EDGE
    else:
        return BrowserType.CHROME


@pytest.fixture(scope="session")
def cdp_port() -> int:
    """Get CDP port from config."""
    return get_config()["cdp_port"]


@pytest.fixture(scope="session")
def base_url() -> str:
    """Get base URL from config."""
    return get_config()["base_url"]


# ============================================================================
# Context Fixtures
# ============================================================================

@pytest.fixture(scope="function")
async def e2e_context(
    base_url: str,
    cdp_port: int,
    browser_type: BrowserType,
) -> AsyncGenerator[E2ETestContext, None]:
    """Function-scoped E2E test context.

    This is the main fixture for E2E tests. It provides:
    - ctx.pw_page: Playwright Page object for high-level operations
    - ctx.page: CDP Page object for low-level control
    - ctx.cdp: CDP Connector for protocol-level operations

    Example:
        @pytest.mark.asyncio
        async def test_example(self, e2e_context):
            await e2e_context.pw_page.goto(e2e_context.base_url)
            assert await e2e_context.pw_page.title() == "Expected Title"
    """
    config = get_config()
    headless = config["headless"]

    ctx = E2ETestContext(
        base_url=base_url,
        cdp_port=cdp_port,
        headless=headless,
        browser_type=browser_type,
    )

    await ctx.__aenter__()
    yield ctx
    await ctx.__aexit__(None, None, None)


@pytest.fixture(scope="function")
async def cdp_page(cdp_port: int) -> AsyncGenerator[CDPPage, None]:
    """Fixture that provides direct CDP page access.

    Use this when you need low-level CDP control without Playwright.

    Example:
        @pytest.mark.asyncio
        async def test_with_cdp(self, cdp_page):
            await cdp_page.enable()
            await cdp_page.navigate("https://example.com")
            title = await cdp_page.evaluate("document.title")
            assert "Example" in title
    """
    ws_url = BrowserLauncher.get_cdp_ws_url(cdp_port)
    cdp = CDPConnector(ws_url)
    await cdp.connect()

    page = CDPPage(cdp)
    await page.enable()

    yield page

    await cdp.close()


@pytest.fixture(scope="function")
async def pw_page(e2e_context: E2ETestContext):
    """Shorthand fixture for Playwright page."""
    return e2e_context.pw_page


# ============================================================================
# Auth Fixtures
# ============================================================================

@pytest.fixture
def test_credentials() -> Dict[str, str]:
    """Return test user credentials.

    Override in conftest.py with actual credentials for your environment.
    """
    return {
        "username": os.getenv("TEST_USERNAME", "admin"),
        "password": os.getenv("TEST_PASSWORD", "admin123"),
        "email": os.getenv("TEST_EMAIL", "admin@example.com"),
    }


@pytest.fixture
async def authenticated_context(
    e2e_context: E2ETestContext,
    test_credentials: Dict[str, str],
) -> E2ETestContext:
    """Context with authenticated user.

    This fixture logs in the user before the test runs.

    Example:
        async def test_authenticated_action(self, authenticated_context):
            # User is already logged in
            await authenticated_context.pw_page.goto("/dashboard")
    """
    page = e2e_context.pw_page

    # Navigate to login
    await page.goto(f"{e2e_context.base_url}/login")
    await page.wait_for_load_state("networkidle")

    # Fill login form
    await page.fill('input[name="username"]', test_credentials["username"])
    await page.fill('input[name="password"]', test_credentials["password"])
    await page.click('button[type="submit"]')

    # Wait for redirect
    await page.wait_for_url("**/dashboard**", timeout=10000)

    return e2e_context


# ============================================================================
# Data Fixtures
# ============================================================================

@pytest.fixture
def sample_task_data() -> Dict[str, Any]:
    """Return sample task data for creating tasks."""
    import time
    return {
        "title": f"E2E Test Task {int(time.time())}",
        "description": "Created by automated E2E test",
        "priority": "medium",
        "tags": ["e2e", "automated"],
    }


@pytest.fixture
def sample_skill_data() -> Dict[str, Any]:
    """Return sample skill/workflow data."""
    import time
    return {
        "name": f"Test Skill {int(time.time())}",
        "description": "Automated test skill",
        "nodes": [
            {"id": "start", "type": "start"},
            {"id": "end", "type": "end"},
        ],
        "edges": [],
    }


# ============================================================================
# Cleanup Fixtures
# ============================================================================

@pytest.fixture
def cleanup_callback():
    """Fixture for registering cleanup actions.

    Usage:
        def test_with_cleanup(self, cleanup_callback):
            # Create resource
            task_id = await create_task(...)

            # Register cleanup
            cleanup_callback(lambda: delete_task(task_id))

            # Test continues...
    """
    callbacks = []

    def register(callback):
        callbacks.append(callback)

    yield register

    # Execute cleanup
    for callback in callbacks:
        try:
            callback()
        except Exception as e:
            print(f"Cleanup error: {e}")


# ============================================================================
# Utility Fixtures
# ============================================================================

@pytest.fixture
def wait_for_selector():
    """Helper fixture for waiting on selectors.

    Usage:
        @pytest.mark.asyncio
        async def test_wait(self, pw_page, wait_for_selector):
            await pw_page.goto(url)
            await wait_for_selector(".loading", state="hidden")
    """
    async def _wait(selector: str, state: str = "visible", timeout: int = 5000):
        # This is a placeholder - in real usage, use Playwright's built-in waits
        await asyncio.sleep(0.1)  # Small delay to allow rendering

    return _wait
