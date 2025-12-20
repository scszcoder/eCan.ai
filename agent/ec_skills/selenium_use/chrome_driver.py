from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from browser_use.browser.profile import (
    CHROME_DEFAULT_ARGS,
    CHROME_DISABLE_SECURITY_ARGS,
    CHROME_DETERMINISTIC_RENDERING_ARGS,
    BrowserProfile,
)


def default_chromedriver(
    *,
    browser_profile: BrowserProfile | None = None,
    headless: bool | None = None,
    user_data_dir: str | Path | None = None,
    driver_path: str | Path | None = None,
    extra_args: Iterable[str] | None = None,
    disable_security: bool | None = None,
    deterministic_rendering: bool | None = None,
) -> Any:
    """Return a Chrome WebDriver configured for browser_use Selenium sessions.

    The factory mirrors BrowserProfile defaults so that the Selenium-backed
    session behaves similarly to the Playwright launcher. Remote debugging is
    automatically enabled so BrowserSession can attach via CDP.
    """

    # Import lazily to avoid hard dependency when Selenium is unused.
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service

    profile = browser_profile or BrowserProfile()
    options = Options()

    if headless is None:
        headless = profile.headless
    if headless:
        # Selenium uses add_argument for headless mode in Chrome >=109.
        options.add_argument("--headless=new")

    if profile.executable_path:
        options.binary_location = str(profile.executable_path)

    resolved_user_data_dir = user_data_dir or profile.user_data_dir
    if resolved_user_data_dir:
        options.add_argument(f"--user-data-dir={Path(resolved_user_data_dir)}")

    # Always request a debugger port so we can extract the CDP endpoint.
    options.add_argument("--remote-debugging-port=0")

    # Apply browser_use default switches while deduplicating.
    for arg in CHROME_DEFAULT_ARGS:
        options.add_argument(arg)

    if disable_security is None:
        disable_security = profile.disable_security
    if disable_security:
        for arg in CHROME_DISABLE_SECURITY_ARGS:
            options.add_argument(arg)

    if deterministic_rendering is None:
        deterministic_rendering = profile.deterministic_rendering
    if deterministic_rendering:
        for arg in CHROME_DETERMINISTIC_RENDERING_ARGS:
            options.add_argument(arg)

    if extra_args:
        for arg in extra_args:
            options.add_argument(arg)

    # Align with Playwright masking.
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    service_kwargs: dict[str, Any] = {}
    if driver_path:
        service_kwargs["executable_path"] = str(driver_path)

    service = Service(**service_kwargs)
    return webdriver.Chrome(service=service, options=options)


