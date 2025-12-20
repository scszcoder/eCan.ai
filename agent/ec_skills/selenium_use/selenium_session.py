from __future__ import annotations

from collections.abc import Callable
from typing import Any

from browser_use import BrowserSession  # existing CDP-based session


class SeleniumBrowserSession(BrowserSession):
    """BrowserSession adapter that owns a Selenium WebDriver instance.

    The adapter launches Chrome via Selenium, discovers its remote-debugging
    address, and lets the base BrowserSession connect over CDP as usual.
    """

    def __init__(
        self,
        webdriver_factory: Callable[[], Any],
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        if not callable(webdriver_factory):
            raise TypeError("webdriver_factory must be callable")
        self._webdriver_factory = webdriver_factory
        self._webdriver: Any | None = None

        # Treat this session as attaching to an already-running browser.
        # BrowserSession.reset() clears CDP URLs only when is_local is True;
        # we keep it False so CDP details survive until we explicitly clear them.
        self.browser_profile.is_local = False

    async def start(self) -> None:
        """Start Selenium driver (if needed) then delegate to BrowserSession."""

        if self._webdriver is None:
            self._webdriver = self._webdriver_factory()

        cdp_url = self._extract_cdp_url(self._webdriver)
        if not cdp_url:
            raise RuntimeError("Unable to determine Chrome DevTools endpoint from Selenium capabilities")

        self.browser_profile.cdp_url = cdp_url
        await super().start()

    async def stop(self) -> None:
        """Gracefully stop BrowserSession and shut down Selenium driver."""

        await super().stop()
        self._shutdown_webdriver()

    async def kill(self) -> None:  # pragma: no cover - defensive override
        await super().kill()
        self._shutdown_webdriver()

    @property
    def webdriver(self) -> Any | None:
        """Expose the underlying Selenium WebDriver (read-only)."""

        return self._webdriver

    def _shutdown_webdriver(self) -> None:
        if self._webdriver is not None:
            try:
                self._webdriver.quit()
            finally:
                self._webdriver = None
                self.browser_profile.cdp_url = None

    @staticmethod
    def _extract_cdp_url(driver: Any) -> str | None:
        """Derive the Chrome DevTools endpoint from Selenium capabilities."""

        capabilities = getattr(driver, "capabilities", {}) or {}
        devtools_addr = capabilities.get("se:cdp")
        if not devtools_addr:
            chrome_options = capabilities.get("goog:chromeOptions", {}) or {}
            devtools_addr = chrome_options.get("debuggerAddress")

        if not devtools_addr:
            return None

        if devtools_addr.startswith("ws://") or devtools_addr.startswith("http"):
            return devtools_addr

        return f"http://{devtools_addr}"


