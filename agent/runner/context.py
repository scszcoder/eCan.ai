from selenium import webdriver
from typing import Optional
from dataclasses import dataclass
import os

from browser.views import BrowserState


@dataclass
class RunnerContextConfig:
    wait_timeout: float = 10
    screenshot_path: Optional[str] = None
    window_size: tuple = (1280, 1100)
    user_agent: Optional[str] = None
    headless: bool = False
    cookies_file: Optional[str] = None


@dataclass
class RunnerSession:
    driver: webdriver.Chrome
    cached_state: Optional[BrowserState] = None


class RunnerContext:
    def __init__(self, config: RunnerContextConfig):
        self.config = config
        options = webdriver.ChromeOptions()
        if self.config.headless:
            options.add_argument('--headless')
        if self.config.user_agent:
            options.add_argument(f'user-agent={self.config.user_agent}')
        options.add_argument('--disable-blink-features=AutomationControlled')
        self.driver = webdriver.Chrome(options=options)
        self.driver.set_window_size(*self.config.window_size)
        self.session = RunnerSession(driver=self.driver)
        if self.config.cookies_file:
            self._load_cookies()
        self._inject_scripts()

    def close(self):
        if self.config.cookies_file:
            self._save_cookies()
        self.driver.quit()

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
