from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from typing import Optional, List
from dataclasses import dataclass
import base64
import os
import time
import json
import re

from dom.views import DOMElementNode, SelectorMap
from dom.service import DomService
from browser.views import BrowserState, BrowserError, TabInfo


@dataclass
class BrowserContextConfig:
    wait_timeout: float = 10
    screenshot_path: Optional[str] = None
    window_size: tuple = (1280, 1100)
    user_agent: Optional[str] = None
    headless: bool = False
    cookies_file: Optional[str] = None


@dataclass
class BrowserSession:
    driver: webdriver.Chrome
    cached_state: Optional[BrowserState] = None


class BrowserContext:
    def __init__(self, config: BrowserContextConfig):
        self.config = config
        options = webdriver.ChromeOptions()
        if self.config.headless:
            options.add_argument('--headless')
        if self.config.user_agent:
            options.add_argument(f'user-agent={self.config.user_agent}')
        options.add_argument('--disable-blink-features=AutomationControlled')
        self.driver = webdriver.Chrome(options=options)
        self.driver.set_window_size(*self.config.window_size)
        self.session = BrowserSession(driver=self.driver)
        if self.config.cookies_file:
            self._load_cookies()
        self._inject_scripts()

    def close(self):
        if self.config.cookies_file:
            self._save_cookies()
        self.driver.quit()

    def _inject_scripts(self):
        try:
            self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": """
                    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                    Object.defineProperty(navigator, 'languages', {get: () => ['en-US']});
                    Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                    window.chrome = { runtime: {} };
                """
            })
        except Exception as e:
            print(f"Failed to inject scripts: {e}")

    def _load_cookies(self):
        if os.path.exists(self.config.cookies_file):
            try:
                with open(self.config.cookies_file, 'r') as f:
                    cookies = json.load(f)
                    self.driver.get("https://www.google.com")
                    for cookie in cookies:
                        if 'sameSite' in cookie and cookie['sameSite'] not in ['Strict', 'Lax', 'None']:
                            cookie['sameSite'] = 'None'
                        self.driver.add_cookie(cookie)
            except Exception as e:
                print(f"Failed to load cookies: {e}")

    def _save_cookies(self):
        try:
            cookies = self.driver.get_cookies()
            with open(self.config.cookies_file, 'w') as f:
                json.dump(cookies, f)
        except Exception as e:
            print(f"Failed to save cookies: {e}")

    def reset_context(self):
        self.driver.delete_all_cookies()
        self.session.cached_state = None

    def _get_unique_filename(self, directory: str, filename: str) -> str:
        base, ext = os.path.splitext(filename)
        counter = 1
        new_filename = filename
        while os.path.exists(os.path.join(directory, new_filename)):
            new_filename = f'{base} ({counter}){ext}'
            counter += 1
        return new_filename

    def _enhanced_css_selector_for_element(self, element: DOMElementNode, include_dynamic_attributes: bool = True) -> str:
        try:
            selector = element.tag_name
            if 'id' in element.attributes:
                return f"#{element.attributes['id']}"
            if 'class' in element.attributes and include_dynamic_attributes:
                classes = element.attributes['class'].split()
                for cls in classes:
                    if cls:
                        selector += f".{cls}"
            SAFE_ATTRIBUTES = {
                'name', 'type', 'placeholder', 'role', 'aria-label', 'aria-labelledby',
                'aria-describedby', 'title', 'alt', 'src', 'href', 'target', 'autocomplete'
            }
            for attr, value in element.attributes.items():
                if attr in SAFE_ATTRIBUTES:
                    selector += f"[{attr}='{value}']"
            return selector
        except Exception:
            return f"{element.tag_name}[highlight_index='{element.highlight_index}']"

    def get_locate_element(self, element: DOMElementNode) -> Optional[WebElement]:
        selector = self._enhanced_css_selector_for_element(element)
        try:
            return self.driver.find_element(By.CSS_SELECTOR, selector)
        except Exception:
            return None

    def get_locate_element_by_css_selector(self, css_selector: str) -> Optional[WebElement]:
        try:
            return self.driver.find_element(By.CSS_SELECTOR, css_selector)
        except Exception:
            return None

    def _input_text_element_node(self, element: DOMElementNode, text: str):
        el = self.get_locate_element(element)
        if not el:
            raise BrowserError(f"Element not found for input: {element}")
        el.clear()
        el.send_keys(text)

    def is_file_uploader(self, element: DOMElementNode, max_depth: int = 3, current_depth: int = 0) -> bool:
        if current_depth > max_depth:
            return False
        if not isinstance(element, DOMElementNode):
            return False
        if element.tag_name == 'input' and (
            element.attributes.get('type') == 'file' or 'accept' in element.attributes
        ):
            return True
        for child in element.children:
            if isinstance(child, DOMElementNode):
                if self.is_file_uploader(child, max_depth, current_depth + 1):
                    return True
        return False

    def _get_cdp_targets(self) -> list:
        try:
            return self.driver.execute_cdp_cmd("Target.getTargets", {})['targetInfos']
        except Exception as e:
            print(f"Failed to get CDP targets: {e}")
            return []
