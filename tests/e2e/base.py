"""E2E Test Base Classes - Shared base classes for E2E tests.

This module provides base classes that implement common patterns for E2E testing.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

import pytest

logger = logging.getLogger(__name__)


class E2ETestMixin(ABC):
    """Mixin providing common E2E test utilities.

    Inherit from this class to get access to common test methods.
    """

    @property
    @abstractmethod
    def page(self):
        """Return the Playwright page object."""
        pass

    @property
    @abstractmethod
    def base_url(self) -> str:
        """Return the base URL."""
        pass

    async def goto(self, path: str, wait_until: str = "networkidle") -> None:
        """Navigate to a path relative to base_url.

        Args:
            path: Path to navigate to (e.g., '/tasks' or '/tasks/new')
            wait_until: When to consider navigation complete
        """
        url = f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"
        await self.page.goto(url, wait_until=wait_until)
        logger.debug(f"Navigated to: {url}")

    async def wait_for_url(self, pattern: str, timeout: int = 10000) -> None:
        """Wait for URL to match pattern.

        Args:
            pattern: URL pattern to match (supports glob)
            timeout: Maximum wait time in milliseconds
        """
        await self.page.wait_for_url(pattern, timeout=timeout)
        logger.debug(f"URL matched: {pattern}")

    async def click_and_wait(self, selector: str, expected_url: str = None) -> None:
        """Click element and optionally wait for URL change.

        Args:
            selector: CSS selector for element to click
            expected_url: Optional URL pattern to wait for after click
        """
        if expected_url:
            async with self.page.expect_navigation(url=expected_url, timeout=10000):
                await self.page.click(selector)
        else:
            await self.page.click(selector)
        logger.debug(f"Clicked: {selector}")

    async def fill_form(self, data: Dict[str, str]) -> None:
        """Fill form fields from dictionary.

        Args:
            data: Dictionary of {selector: value} pairs
        """
        for selector, value in data.items():
            await self.page.fill(selector, value)
        logger.debug(f"Filled form with {len(data)} fields")

    async def get_text(self, selector: str) -> str:
        """Get text content of element."""
        return await self.page.text_content(selector)

    async def is_visible(self, selector: str) -> bool:
        """Check if element is visible."""
        return await self.page.is_visible(selector)

    async def count_elements(self, selector: str) -> int:
        """Count elements matching selector."""
        return await self.page.locator(selector).count()

    async def screenshot(self, name: str = None) -> bytes:
        """Take screenshot of current page.

        Args:
            name: Optional name for screenshot file

        Returns:
            Screenshot as bytes
        """
        return await self.page.screenshot()


class PageObject(ABC):
    """Base class for Page Objects.

    Page Objects encapsulate the structure and behavior of a page,
    providing a clean API for test code.
    """

    def __init__(self, page, base_path: str = ""):
        """Initialize Page Object.

        Args:
            page: Playwright page object
            base_path: Base path for this page
        """
        self._page = page
        self._base_path = base_path

    @property
    def page(self):
        """Get the page object."""
        return self._page

    @property
    @abstractmethod
    def url(self) -> str:
        """Return the URL pattern for this page."""
        pass

    async def navigate(self) -> None:
        """Navigate to this page."""
        await self._page.goto(self.url)
        await self._page.wait_for_load_state("networkidle")

    async def is_loaded(self) -> bool:
        """Check if page is loaded."""
        try:
            await self._page.wait_for_load_state("domcontentloaded", timeout=5000)
            return True
        except Exception:
            return False


class ComponentObject(ABC):
    """Base class for reusable UI components."""

    def __init__(self, page, root_selector: str):
        """Initialize Component Object.

        Args:
            page: Playwright page object
            root_selector: CSS selector for component root
        """
        self._page = page
        self._root_selector = root_selector

    def locator(self, selector: str):
        """Get locator for element within component."""
        return self._page.locator(f"{self._root_selector} {selector}")

    @property
    def is_visible(self) -> bool:
        """Check if component is visible."""
        return self._page.is_visible(self._root_selector)


# ============================================================================
# Test Base Classes
# ============================================================================

class BaseE2ETest(ABC):
    """Base class for E2E tests using the E2ETestMixin.

    Example:
        class TestLogin(BaseE2ETest):
            @pytest.fixture(autouse=True)
            async def setup(self, e2e_context):
                self.ctx = e2e_context

            @property
            def page(self):
                return self.ctx.pw_page

            @property
            def base_url(self) -> str:
                return self.ctx.base_url
    """

    @property
    @abstractmethod
    def page(self):
        """Return the Playwright page object."""
        pass

    @property
    @abstractmethod
    def base_url(self) -> str:
        """Return the base URL."""
        pass

    def log(self, message: str) -> None:
        """Log a message."""
        logger.info(f"[{self.__class__.__name__}] {message}")


class ComponentTest(ABC):
    """Base class for component-level tests."""

    @property
    @abstractmethod
    def page(self):
        """Return the Playwright page object."""
        pass

    @property
    @abstractmethod
    def component_selector(self) -> str:
        """Return CSS selector for component root."""
        pass
