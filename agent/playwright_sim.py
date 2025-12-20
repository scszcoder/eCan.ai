
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium import webdriver
import time
from typing import List
from typing import TYPE_CHECKING, Optional


if TYPE_CHECKING:
    pass

from utils.logger_helper import logger_helper as logger


class Page:
    def __init__(self, driver: WebDriver, handle=None, url="", timeout: int = 10):
        self.driver = driver
        self.timeout = timeout
        self.handle = handle
        self.url = url

    def goto(self, url: str):
        self.driver.get(url)

    def content(self) -> str:
        return self.driver.page_source

    def title(self) -> str:
        return self.driver.title

    def url(self) -> str:
        return self.driver.current_url

    def screenshot(self, path: str = "screenshot.png"):
        self.driver.save_screenshot(path)

    def locator(self, by: str, value: str) -> WebElement:
        return self.driver.find_element(by, value)

    def locator_all(self, by: str, value: str) -> list[WebElement]:
        return self.driver.find_elements(by, value)

    def wait_for_selector(self, by: str, value: str) -> WebElement:
        try:
            return WebDriverWait(self.driver, self.timeout).until(
                EC.visibility_of_element_located((by, value))
            )
        except TimeoutException:
            raise TimeoutError(f"Element {value} not visible within {self.timeout}s")

    def wait_for_load_state(self, act):
        WebDriverWait(self.driver, 10).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )

    def evaluate(self, script: str, *args):
        return self.driver.execute_script(script, *args)

    def reload(self):
        self.driver.refresh()

    def go_back(self):
        self.driver.back()

    def go_forward(self):
        self.driver.forward()

    def close(self):
        self.driver.close()

    def bring_to_front(self):
        # Selenium opens one tab by default; if multi-tabs used, bring active
        self.driver.switch_to.window(self.driver.current_window_handle)


class ElementHandle:
    def __init__(self, selenium_element, driver):
        self._element = selenium_element  # selenium.webdriver.remote.webelement.WebElement
        self._driver = driver             # selenium.webdriver instance

    def is_visible(self) -> bool:
        return self._element.is_displayed()

    def click(self, timeout=1500):
        self.scroll_into_view_if_needed()
        self._element.click()

    def fill(self, text: str):
        self._element.clear()
        self._element.send_keys(text)

    def type(self, text: str, delay: float = 0.05):
        import time
        self._element.clear()
        for char in text:
            self._element.send_keys(char)
            time.sleep(delay)

    def get_property(self, name: str):
        return self._driver.execute_script("return arguments[0][arguments[1]];", self._element, name)

    def evaluate(self, script: str):
        return self._driver.execute_script(script, self._element)

    def scroll_into_view_if_needed(self, timeout: float = 1.0):
        self._driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", self._element)

    def __repr__(self):
        return f"<ElementHandle tag={self._element.tag_name} text='{self._element.text[:30]}...'>"




class SeleniumTabInfo:
    def __init__(self, handle: str, url: str = '', title: str = ''):
        self.handle = handle
        self.url = url
        self.title = title

    def __repr__(self):
        return f"{self.title} ({self.url})"


class PlaywrightBrowserContext:
    def __init__(self, driver: WebDriver):
        self.driver = driver
        self.active_tab = driver.current_window_handle

    def get_current_page(self) -> WebDriver:
        self.driver.switch_to.window(self.active_tab)
        return self.driver

    def switch_to_tab(self, handle: str) -> None:
        self.driver.switch_to.window(handle)
        self.active_tab = handle

    def get_tabs_info(self) -> List[SeleniumTabInfo]:
        tabs = []
        original = self.driver.current_window_handle
        for handle in self.driver.window_handles:
            self.driver.switch_to.window(handle)
            time.sleep(0.5)
            tabs.append(SeleniumTabInfo(handle, self.driver.current_url, self.driver.title))
        self.driver.switch_to.window(original)
        return tabs

    def create_new_tab(self, url: Optional[str] = None) -> None:
        self.driver.execute_script("window.open('');")
        handles = self.driver.window_handles
        new_tab = handles[-1]
        self.driver.switch_to.window(new_tab)
        self.active_tab = new_tab
        if url:
            self.driver.get(url)

    def close_current_tab(self) -> None:
        self.driver.close()
        remaining = self.driver.window_handles
        if remaining:
            self.driver.switch_to.window(remaining[0])
            self.active_tab = remaining[0]

    def get_state(self) -> dict:
        current = self.get_current_page()
        screenshot_b64 = current.get_screenshot_as_base64()
        return {
            "url": current.current_url,
            "title": current.title,
            "tabs": self.get_tabs_info(),
            "screenshot": screenshot_b64,
        }

    def take_browser_screenshot(self, full_page: bool = False) -> str:
        # NOTE: full_page capture would need scrolling and stitching, so we skip it here
        return self.driver.get_screenshot_as_base64()



class PlaywrightBrowser:
    def __init__(self, driver: Optional[webdriver.Chrome] = None):
        self.driver = driver or self._create_driver()
        self.contexts: List[PlaywrightBrowserContext] = []

    def _create_driver(self) -> webdriver.Chrome:
        options = Options()
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        # options.add_argument('--headless')  # Optional: Uncomment for headless mode
        return webdriver.Chrome(options=options)

    def new_context(self) -> PlaywrightBrowserContext:
        context = PlaywrightBrowserContext(self.driver)
        self.contexts.append(context)
        return context

    def close(self) -> None:
        if self.driver:
            self.driver.quit()
            self.driver = None
            self.contexts.clear()

    def __del__(self):
        self.close()

    @property
    def current_context(self) -> Optional[PlaywrightBrowserContext]:
        return self.contexts[-1] if self.contexts else None