from __future__ import annotations

from typing import Any, Iterable

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


class SeleniumTools:
    """Utility helpers mirroring common browser_use tool semantics for Selenium."""

    def __init__(self, webdriver: WebDriver, default_timeout: float = 10.0) -> None:
        self.webdriver = webdriver
        self.default_timeout = default_timeout

    def _locator(self, selector: str, by: str | None = None) -> tuple[str, str]:
        strategy = by or By.CSS_SELECTOR
        return strategy, selector

    def _wait_for_element(
        self,
        locator: tuple[str, str],
        timeout: float | None = None,
        condition: Any = None,
    ) -> WebElement:
        wait = WebDriverWait(self.webdriver, timeout or self.default_timeout)
        cond = condition or EC.presence_of_element_located(locator)
        return wait.until(cond)

    async def click(
        self,
        selector: str,
        *,
        by: str | None = None,
        timeout: float | None = None,
        scroll_into_view: bool = True,
    ) -> WebElement:
        element = self._wait_for_element(self._locator(selector, by), timeout, EC.element_to_be_clickable(self._locator(selector, by)))
        if scroll_into_view:
            self.webdriver.execute_script(
                "arguments[0].scrollIntoView({block: 'center', inline: 'nearest'});",
                element,
            )
        element.click()
        return element

    async def fill(
        self,
        selector: str,
        value: str,
        *,
        by: str | None = None,
        timeout: float | None = None,
        clear: bool = True,
    ) -> WebElement:
        element = self._wait_for_element(self._locator(selector, by), timeout)
        if clear:
            try:
                element.clear()
            except Exception:
                pass
        element.send_keys(value)
        return element

    async def text(self, selector: str, *, by: str | None = None, timeout: float | None = None) -> str:
        element = self._wait_for_element(self._locator(selector, by), timeout, EC.visibility_of_element_located(self._locator(selector, by)))
        return element.text

    async def wait_for_visible(self, selector: str, *, by: str | None = None, timeout: float | None = None) -> WebElement:
        return self._wait_for_element(self._locator(selector, by), timeout, EC.visibility_of_element_located(self._locator(selector, by)))

    async def wait_for_disappear(self, selector: str, *, by: str | None = None, timeout: float | None = None) -> bool:
        wait = WebDriverWait(self.webdriver, timeout or self.default_timeout)
        try:
            return wait.until(EC.invisibility_of_element_located(self._locator(selector, by)))
        except TimeoutException:
            return False

    async def query_all(self, selector: str, *, by: str | None = None) -> Iterable[WebElement]:
        return self.webdriver.find_elements(*(self._locator(selector, by)))

    async def execute_script(self, script: str, *args: Any) -> Any:
        return self.webdriver.execute_script(script, *args)