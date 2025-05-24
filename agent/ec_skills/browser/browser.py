from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from typing import Optional
import os
import logging
from typing import Literal

# from playwright.async_api import (
# 	Playwright,
# 	async_playwright,
# )
from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from agent.ec_skills.browser.context import BrowserContext, BrowserContextConfig

logger = logging.getLogger(__name__)

IN_DOCKER = os.environ.get('IN_DOCKER', 'false').lower()[0] in 'ty1'


class ProxySettings(BaseModel):
	"""the same as playwright.sync_api.ProxySettings, but now as a Pydantic BaseModel so pydantic can validate it"""

	server: str
	bypass: str | None = None
	username: str | None = None
	password: str | None = None

	model_config = ConfigDict(populate_by_name=True, from_attributes=True)

	# Support dict-like behavior for compatibility with Playwright's ProxySettings
	def __getitem__(self, key):
		return getattr(self, key)

	def get(self, key, default=None):
		return getattr(self, key, default)


class BrowserConfig(BaseModel):
    r"""
	Configuration for the Browser.

	Default values:
		headless: False
			Whether to run browser in headless mode (not recommended)

		disable_security: False
			Disable browser security features (required for cross-origin iframe support)

		extra_browser_args: []
			Extra arguments to pass to the browser

		wss_url: None
			Connect to a browser instance via WebSocket

		cdp_url: None
			Connect to a browser instance via CDP

		browser_binary_path: None
			Path to a Browser instance to use to connect to your normal browser
			e.g. '/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome'

		keep_alive: False
			Keep the browser alive after the agent has finished running

		deterministic_rendering: False
			Enable deterministic rendering (makes GPU/font rendering consistent across different OS's and docker)
	"""

    model_config = ConfigDict(
		arbitrary_types_allowed=True,
		extra='ignore',
		populate_by_name=True,
		from_attributes=True,
		validate_assignment=True,
		revalidate_instances='subclass-instances',
	)

    wss_url: str | None = None
    cdp_url: str | None = None

    browser_class: Literal['chromium', 'firefox', 'webkit'] = 'chromium'
    browser_binary_path: str | None = Field(default=None, alias=AliasChoices('browser_instance_path', 'chrome_instance_path'))
    extra_browser_args: list[str] = Field(default_factory=list)

    headless: bool = False
    disable_security: bool = False  # disable_security=True is dangerous as any malicious URL visited could embed an iframe for the user's bank, and use their cookies to steal money
    deterministic_rendering: bool = False
    keep_alive: bool = Field(default=False, alias='_force_keep_browser_alive')  # used to be called _force_keep_browser_alive

    proxy: ProxySettings | None = None
    new_context_config: BrowserContextConfig = Field(default_factory=BrowserContextConfig)


class Browser:
    def __init__(self, config: Optional[BrowserConfig] = None):
        logger.debug('🌎  Initializing new Selenium browser')
        self.config = config or BrowserConfig()
        self.driver: Optional[webdriver.Chrome] = None
        self.contexts = []

    async def get_chrome_browser(self):
        return self.driver

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

    async def new_context(self, config: Optional[BrowserContextConfig] = None, **kwargs) -> BrowserContext:
        config = config or self.config.new_context_config

        # Convert to dict, update with kwargs, and re-parse into a model
        config_data = config.model_dump()
        config_data.update(kwargs)
        config = BrowserContextConfig(**config_data)

        driver = self._setup_driver()
        return BrowserContext(self, config=config)

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