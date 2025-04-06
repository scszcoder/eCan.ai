from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.common.by import By
from typing import Optional, Literal
from dataclasses import dataclass, field
import os
import json
import logging
import subprocess
import socket
import time

from browser.context import BrowserContext, BrowserContextConfig

logger = logging.getLogger(__name__)

@dataclass
class BrowserConfig:
    headless: bool = False
    disable_security: bool = False
    browser_binary_path: Optional[str] = None
    extra_browser_args: list[str] = field(default_factory=list)
    keep_alive: bool = False
    proxy: Optional[str] = None
    new_context_config: BrowserContextConfig = field(default_factory=BrowserContextConfig)


class Browser:
    def __init__(self, config: Optional[BrowserConfig] = None):
        logger.debug('🌎  Initializing new Selenium browser')
        self.config = config or BrowserConfig()
        self.driver: Optional[webdriver.Chrome] = None

    def _build_chrome_options(self) -> ChromeOptions:
        options = ChromeOptions()
        if self.config.headless:
            options.add_argument('--headless')
        if self.config.disable_security:
            options.add_argument('--disable-web-security')
            options.add_argument('--disable-site-isolation-trials')
        if self.config.proxy:
            options.add_argument(f'--proxy-server={self.config.proxy}')
        if self.config.browser_binary_path:
            options.binary_location = self.config.browser_binary_path
        for arg in self.config.extra_browser_args:
            options.add_argument(arg)
        return options

    def _setup_driver(self):
        if self.driver is not None:
            return self.driver

        options = self._build_chrome_options()
        service = ChromeService()
        self.driver = webdriver.Chrome(service=service, options=options)
        return self.driver

    def new_context(self, config: Optional[BrowserContextConfig] = None) -> BrowserContext:
        config = config or self.config.new_context_config
        driver = self._setup_driver()
        return BrowserContext(config=config, driver=driver)

    def close(self):
        if not self.config.keep_alive and self.driver:
            try:
                self.driver.quit()
            except Exception as e:
                logger.debug(f"Failed to close Selenium driver: {e}")
            finally:
                self.driver = None

    def __del__(self):
        try:
            self.close()
        except Exception as e:
            logger.debug(f"Failed to cleanup browser in destructor: {e}")