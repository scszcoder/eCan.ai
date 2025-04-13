from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from typing import Optional, List
from typing import TYPE_CHECKING, Optional
from dataclasses import dataclass
import base64
import os
import time
import json
import re
import gc
import uuid
import logging
from dom.views import DOMElementNode, SelectorMap
from dom.service import DomService
from browser.views import BrowserState, BrowserError, TabInfo
from agent.run_utils import time_execution_sync
import traceback
from pydantic import BaseModel, ConfigDict, Field
from agent.playwright_sim import *
import asyncio
from browser.views import (
	BrowserError,
	BrowserState,
	TabInfo,
	URLNotAllowedError,
)
from dom.service import DomService
from dom.views import DOMElementNode, SelectorMap
from agent.run_utils import time_execution_async, time_execution_sync

if TYPE_CHECKING:
	from browser.browser import Browser

logger = logging.getLogger(__name__)


class BrowserContextWindowSize(BaseModel):
	"""Window size configuration for browser context"""

	width: int
	height: int

	model_config = ConfigDict(
		extra='allow',  # Allow extra fields to ensure compatibility with dictionary
		populate_by_name=True,
		from_attributes=True,
	)

	# Support dict-like behavior for compatibility
	def __getitem__(self, key):
		return getattr(self, key)

	def get(self, key, default=None):
		return getattr(self, key, default)

class BrowserContextConfig(BaseModel):
    """
	Configuration for the BrowserContext.

	Default values:
	    cookies_file: None
	        Path to cookies file for persistence

		disable_security: False
			Disable browser security features (dangerous, but cross-origin iframe support requires it)

	    minimum_wait_page_load_time: 0.5
	        Minimum time to wait before getting page state for LLM input

		wait_for_network_idle_page_load_time: 1.0
			Time to wait for network requests to finish before getting page state.
			Lower values may result in incomplete page loads.

	    maximum_wait_page_load_time: 5.0
	        Maximum time to wait for page load before proceeding anyway

	    wait_between_actions: 1.0
	        Time to wait between multiple per step actions

	    browser_window_size: {'width': 1280, 'height': 1100}
	        Default browser window size

	    no_viewport: False
	        Disable viewport

	    save_recording_path: None
	        Path to save video recordings

	    save_downloads_path: None
	        Path to save downloads to

	    trace_path: None
	        Path to save trace files. It will auto name the file with the TRACE_PATH/{context_id}.zip

	    locale: None
	        Specify user locale, for example en-GB, de-DE, etc. Locale will affect navigator.language value, Accept-Language request header value as well as number and date formatting rules. If not provided, defaults to the system default locale.

	    user_agent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/85.0.4183.102 Safari/537.36'
	        custom user agent to use.

	    highlight_elements: True
	        Highlight elements in the DOM on the screen

	    viewport_expansion: 0
	        Viewport expansion in pixels. This amount will increase the number of elements which are included in the state what the LLM will see. If set to -1, all elements will be included (this leads to high token usage). If set to 0, only the elements which are visible in the viewport will be included.

	    allowed_domains: None
	        List of allowed domains that can be accessed. If None, all domains are allowed.
	        Example: ['example.com', 'api.example.com']

	    include_dynamic_attributes: bool = True
	        Include dynamic attributes in the CSS selector. If you want to reuse the css_selectors, it might be better to set this to False.

		  http_credentials: None
	  Dictionary with HTTP basic authentication credentials for corporate intranets (only supports one set of credentials for all URLs at the moment), e.g.
	  {"username": "bill", "password": "pa55w0rd"}

	    is_mobile: None
	        Whether the meta viewport tag is taken into account and touch events are enabled.

	    has_touch: None
	        Whether to enable touch events in the browser.

	    geolocation: None
	        Geolocation to be used in the browser context. Example: {'latitude': 59.95, 'longitude': 30.31667}

	    permissions: None
	        Browser permissions to grant. Values might include: ['geolocation', 'notifications']

	    timezone_id: None
	        Changes the timezone of the browser. Example: 'Europe/Berlin'
	"""

    model_config = ConfigDict(
		arbitrary_types_allowed=True,
		extra='ignore',
		populate_by_name=True,
		from_attributes=True,
		validate_assignment=True,
		revalidate_instances='subclass-instances',
	)

    cookies_file: str | None = None
    minimum_wait_page_load_time: float = 0.25
    wait_for_network_idle_page_load_time: float = 0.5
    maximum_wait_page_load_time: float = 5
    wait_between_actions: float = 0.5

    disable_security: bool = False  # disable_security=True is dangerous as any malicious URL visited could embed an iframe for the user's bank, and use their cookies to steal money

    browser_window_size: BrowserContextWindowSize = Field(
		default_factory=lambda: BrowserContextWindowSize(width=1280, height=1100)
	)
    no_viewport: Optional[bool] = None

    save_recording_path: str | None = None
    save_downloads_path: str | None = None
    save_har_path: str | None = None
    trace_path: str | None = None
    locale: str | None = None
    user_agent: str = (
		'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36  (KHTML, like Gecko) Chrome/85.0.4183.102 Safari/537.36'
	)

    highlight_elements: bool = True
    viewport_expansion: int = 0
    allowed_domains: list[str] | None = None
    include_dynamic_attributes: bool = True
    http_credentials: dict[str, str] | None = None

    keep_alive: bool = Field(default=False, alias='_force_keep_context_alive')  # used to be called _force_keep_context_alive
    is_mobile: bool | None = None
    has_touch: bool | None = None
    geolocation: dict | None = None
    permissions: list[str] | None = None
    timezone_id: str | None = None

    wait_timeout: float = 10
    screenshot_path: Optional[str] = None
    window_size: tuple = (1280, 1100)
    headless: bool = False


class BrowserSession:
    def __init__(self, context: PlaywrightBrowserContext, cached_state: BrowserState | None = None):
        init_script = """
			(() => {
				if (!window.getEventListeners) {
					window.getEventListeners = function (node) {
						return node.__listeners || {};
					};

					// Save the original addEventListener
					const originalAddEventListener = Element.prototype.addEventListener;

					const eventProxy = {
						addEventListener: function (type, listener, options = {}) {
							// Initialize __listeners if not exists
							const defaultOptions = { once: false, passive: false, capture: false };
							if(typeof options === 'boolean') {
								options = { capture: options };
							}
							options = { ...defaultOptions, ...options };
							if (!this.__listeners) {
								this.__listeners = {};
							}

							// Initialize array for this event type if not exists
							if (!this.__listeners[type]) {
								this.__listeners[type] = [];
							}
							

							// Add the listener to __listeners
							this.__listeners[type].push({
								listener: listener,
								type: type,
								...options
							});

							// Call original addEventListener using the saved reference
							return originalAddEventListener.call(this, type, listener, options);
						}
					};

					Element.prototype.addEventListener = eventProxy.addEventListener;
				}
			})()
			"""

        self.active_tab = None
        self.context = context
        self.cached_state = cached_state
        self.pages = []
        # self.context.on('page', lambda page: page.add_init_script(init_script))
        # driver.execute_script(init_script)

        # driver: webdriver.Chrome
        # cached_state: Optional[BrowserState] = None

    async def new_page(self):
        print("open a new tab")

@dataclass
class BrowserContextState:
    """
	State of the browser context
	"""
    target_id: str | None = None  # CDP target ID

class BrowserContext:
    def __init__(self, browser: 'Browser', config: BrowserContextConfig, state: Optional[BrowserContextState] = None,):
        self.context_id = str(uuid.uuid4())
        self.browser = browser
        self.config = config
        self.state = state or BrowserContextState()
        options = webdriver.ChromeOptions()
        if self.config.headless:
            options.add_argument('--headless')
        if self.config.user_agent:
            options.add_argument(f'user-agent={self.config.user_agent}')
        options.add_argument('--disable-blink-features=AutomationControlled')
        self.driver = webdriver.Chrome(options=options)
        self.driver.set_window_size(*self.config.window_size)
        self.session: BrowserSession | None = None
        self.active_tab: Page | None = None
        if self.config.cookies_file:
            self._load_cookies()
        self._inject_scripts()

    async def __aenter__(self):
        """Async context manager entry"""
        await self._initialize_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()

    def close(self):
        if self.config.cookies_file:
            self._save_cookies()
        self.driver.quit()

    def __del__(self):
        """Cleanup when object is destroyed"""
        if not self.config.keep_alive and self.session is not None:
            logger.debug('BrowserContext was not properly closed before destruction')
            try:
                # Use sync Playwright method for force cleanup
                if hasattr(self.session.context, '_impl_obj'):
                    asyncio.run(self.session.context._impl_obj.close())

                self.session = None
                gc.collect()
            except Exception as e:
                logger.warning(f'Failed to force close browser context: {e}')

    @time_execution_async('--initialize_session')
    async def _initialize_session(self):
        """Initialize the browser session"""
        logger.debug(f'🌎  Initializing new browser context with id: {self.context_id}')

        web_driver = await self.browser.get_chrome_browser()
        context = await self._create_context(self.browser)
        self._page_event_handler = None

        self.session = BrowserSession(
            context=context,
            cached_state=None,
        )

        # Get or create a page to use
        pages = self.session.pages

        active_page = None
        if self.browser.config.cdp_url:
            # If we have a saved target ID, try to find and activate it
            if self.state.target_id:
                targets = await self._get_cdp_targets()
                for target in targets:
                    if target['targetId'] == self.state.target_id:
                        # Find matching page by URL
                        for page in pages:
                            if page.url == target['url']:
                                active_page = page
                                break
                        break

        # If no target ID or couldn't find it, use existing page or create new
        if not active_page:
            if (
                    pages
                    and pages[0].url
                    and not pages[0].url.startswith(
                'chrome://')  # skip chrome internal pages e.g. settings, history, etc
                    and not pages[0].url.startswith('chrome-extension://')  # skip hidden extension background pages
            ):
                active_page = pages[0]
                logger.debug('🔍  Using existing page: %s', active_page.url)
            else:
                # active_page = await context.new_page()
                await self.create_new_tab()
                if active_page:
                    await active_page.goto('about:blank')
                    logger.debug('🆕  Created new page: %s', active_page.url)

            # Get target ID for the active page
            if self.browser.config.cdp_url:
                targets = await self._get_cdp_targets()
                for target in targets:
                    if target['url'] == active_page.url:
                        self.state.target_id = target['targetId']
                        break

        # Bring page to front
        logger.debug('🫨  Bringing tab to front: %s', active_page)
        if active_page:
            await active_page.bring_to_front()
            await active_page.wait_for_load_state('load')

        self.active_tab = active_page

        return self.session

    # selenium has no _add_new_page_listener as in playright, instead
    # we need to call this from time to time to poll
    def check_for_new_tabs(self):
        current_tabs = set(self.driver.window_handles)
        new_tabs = current_tabs - self.known_tabs

        if new_tabs:
            for handle in new_tabs:
                self.driver.switch_to.window(handle)
                self.active_tab = Page(self.driver, handle, self.driver.current_url)

                try:
                    self.driver.refresh()  # Simulate playwright's reload
                    time.sleep(1)  # Basic wait, or use WebDriverWait if needed
                    url = self.driver.current_url
                    logger.debug(f'📑  New page opened: {url}')

                    if not url.startswith('chrome-extension://') and not url.startswith('chrome://'):
                        self.active_tab = Page(self.driver, handle, url)

                    if self.session is not None:
                        self.state.target_id = None

                except Exception as e:
                    logger.warning(f'Failed to handle new tab: {e}')

        self.known_tabs = current_tabs

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

    # def get_locate_element(self, element: DOMElementNode) -> Optional[WebElement]:
    #     selector = self._enhanced_css_selector_for_element(element)
    #     try:
    #         return self.driver.find_element(By.CSS_SELECTOR, selector)
    #     except Exception:
    #         return None

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


    async def _create_context(self, browser):
        """Creates a new browser context with anti-detection measures and loads cookies if available."""
        print("creating context...................................")
        if self.browser.config.cdp_url and len(browser.contexts) > 0:
            context = browser.contexts[0]
        elif self.browser.config.browser_binary_path and len(browser.contexts) > 0:
            # Connect to existing Chrome instance instead of creating new one
            context = browser.contexts[0]
        else:
            # Original code for creating new context
            print("creating NEW  context...................................")
            context = await browser.new_context(
                no_viewport=True,
                user_agent=self.config.user_agent,
                java_script_enabled=True,
                bypass_csp=self.config.disable_security,
                ignore_https_errors=self.config.disable_security,
                record_video_dir=self.config.save_recording_path,
                record_video_size=self.config.browser_window_size.model_dump(),
                record_har_path=self.config.save_har_path,
                locale=self.config.locale,
                http_credentials=self.config.http_credentials,
                is_mobile=self.config.is_mobile,
                has_touch=self.config.has_touch,
                geolocation=self.config.geolocation,
                permissions=self.config.permissions,
                timezone_id=self.config.timezone_id,
            )

        if self.config.trace_path:
            await context.tracing.start(screenshots=True, snapshots=True, sources=True)

        # Load cookies if they exist
        if self.config.cookies_file and os.path.exists(self.config.cookies_file):
            with open(self.config.cookies_file, 'r') as f:
                try:
                    cookies = json.load(f)

                    valid_same_site_values = ['Strict', 'Lax', 'None']
                    for cookie in cookies:
                        if 'sameSite' in cookie:
                            if cookie['sameSite'] not in valid_same_site_values:
                                logger.warning(
                                    f"Fixed invalid sameSite value '{cookie['sameSite']}' to 'None' for cookie {cookie.get('name')}"
                                )
                                cookie['sameSite'] = 'None'
                    logger.info(f'🍪  Loaded {len(cookies)} cookies from {self.config.cookies_file}')
                    await context.add_cookies(cookies)

                except json.JSONDecodeError as e:
                    logger.error(f'Failed to parse cookies file: {str(e)}')

        # Expose anti-detection scripts
        # await context.add_init_script(
        # self.driver.execute_script(
        self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source":

            """
            // Webdriver property
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });

            // Languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US']
            });

            // Plugins
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });

            // Chrome runtime
            window.chrome = { runtime: {} };

            // Permissions
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );
            (function () {
                const originalAttachShadow = Element.prototype.attachShadow;
                Element.prototype.attachShadow = function attachShadow(options) {
                    return originalAttachShadow.call(this, { ...options, mode: "open" });
                };
            })();
            """
        })

        return context


    async def get_session(self) -> BrowserSession:
        """Lazy initialization of the browser and related components"""
        if self.session is None:
            try:
                return await self._initialize_session()
            except Exception as e:
                traceback_info = traceback.extract_tb(e.__traceback__)
                # Extract the file name and line number from the last entry in the traceback
                if traceback_info:
                    ex_stat = "ErrorFetchSchedule:" + traceback.format_exc() + " " + str(e)
                    logger.error(f'❌  Failed to create new browser session: {ex_stat} (did the browser process quit?)')
                raise e
        return self.session

    async def get_current_page(self) -> Page:
        """Get the current page"""
        session = await self.get_session()
        return await self._get_current_page(session)

    async def _create_driver(self) -> webdriver.Chrome:
        """
        Creates a new Selenium WebDriver instance with custom options,
        simulating Playwright context features as closely as possible.
        """
        options = Options()

        # Set binary path if provided
        if self.config.browser_binary_path:
            options.binary_location = self.config.browser_binary_path

        # User agent spoofing
        if self.config.user_agent:
            options.add_argument(f"user-agent={self.config.user_agent}")

        # Headless or not
        options.add_argument("--disable-blink-features=AutomationControlled")
        if self.config.disable_security:
            options.add_argument("--ignore-certificate-errors")
            options.add_argument("--disable-web-security")
            options.add_argument("--allow-running-insecure-content")

        # Locale and timezone (simulated via JS or Chrome extensions if needed)
        # You can use extensions or CDP (Chrome DevTools Protocol) for this

        # Launch driver
        driver = webdriver.Chrome(options=options)

        # Load cookies if file is available
        if self.config.cookies_file and os.path.exists(self.config.cookies_file):
            with open(self.config.cookies_file, 'r') as f:
                try:
                    cookies = json.load(f)
                    driver.get("https://example.com")  # required before adding cookies

                    valid_same_site_values = ['Strict', 'Lax', 'None']
                    for cookie in cookies:
                        # Selenium cookie format validation
                        cookie['sameSite'] = cookie.get('sameSite', 'None')
                        if cookie['sameSite'] not in valid_same_site_values:
                            logger.warning(f"Fixed invalid sameSite value '{cookie['sameSite']}' to 'None' for {cookie.get('name')}")
                            cookie['sameSite'] = 'None'

                        # Optional fields cleanup
                        cookie.pop('expiry', None)  # Optional cleanup if needed
                        try:
                            driver.add_cookie(cookie)
                        except Exception as e:
                            logger.warning(f"Could not set cookie {cookie.get('name')}: {e}")

                    logger.info(f'🍪  Loaded {len(cookies)} cookies from {self.config.cookies_file}')

                except json.JSONDecodeError as e:
                    logger.error(f'Failed to parse cookies file: {str(e)}')

        return driver

    async def _wait_for_stable_network(self):
        page = await self.get_current_page()

        pending_requests = set()
        last_activity = asyncio.get_event_loop().time()

        # Define relevant resource types and content types
        RELEVANT_RESOURCE_TYPES = {
            'document',
            'stylesheet',
            'image',
            'font',
            'script',
            'iframe',
        }

        RELEVANT_CONTENT_TYPES = {
            'text/html',
            'text/css',
            'application/javascript',
            'image/',
            'font/',
            'application/json',
        }

        # Additional patterns to filter out
        IGNORED_URL_PATTERNS = {
            # Analytics and tracking
            'analytics',
            'tracking',
            'telemetry',
            'beacon',
            'metrics',
            # Ad-related
            'doubleclick',
            'adsystem',
            'adserver',
            'advertising',
            # Social media widgets
            'facebook.com/plugins',
            'platform.twitter',
            'linkedin.com/embed',
            # Live chat and support
            'livechat',
            'zendesk',
            'intercom',
            'crisp.chat',
            'hotjar',
            # Push notifications
            'push-notifications',
            'onesignal',
            'pushwoosh',
            # Background sync/heartbeat
            'heartbeat',
            'ping',
            'alive',
            # WebRTC and streaming
            'webrtc',
            'rtmp://',
            'wss://',
            # Common CDNs for dynamic content
            'cloudfront.net',
            'fastly.net',
        }

        async def on_request(request):
            # Filter by resource type
            if request.resource_type not in RELEVANT_RESOURCE_TYPES:
                return

            # Filter out streaming, websocket, and other real-time requests
            if request.resource_type in {
                'websocket',
                'media',
                'eventsource',
                'manifest',
                'other',
            }:
                return

            # Filter out by URL patterns
            url = request.url.lower()
            if any(pattern in url for pattern in IGNORED_URL_PATTERNS):
                return

            # Filter out data URLs and blob URLs
            if url.startswith(('data:', 'blob:')):
                return

            # Filter out requests with certain headers
            headers = request.headers
            if headers.get('purpose') == 'prefetch' or headers.get('sec-fetch-dest') in [
                'video',
                'audio',
            ]:
                return

            nonlocal last_activity
            pending_requests.add(request)
            last_activity = asyncio.get_event_loop().time()

        # logger.debug(f'Request started: {request.url} ({request.resource_type})')

        async def on_response(response):
            request = response.request
            if request not in pending_requests:
                return

            # Filter by content type if available
            content_type = response.headers.get('content-type', '').lower()

            # Skip if content type indicates streaming or real-time data
            if any(
                    t in content_type
                    for t in [
                        'streaming',
                        'video',
                        'audio',
                        'webm',
                        'mp4',
                        'event-stream',
                        'websocket',
                        'protobuf',
                    ]
            ):
                pending_requests.remove(request)
                return

            # Only process relevant content types
            if not any(ct in content_type for ct in RELEVANT_CONTENT_TYPES):
                pending_requests.remove(request)
                return

            # Skip if response is too large (likely not essential for page load)
            content_length = response.headers.get('content-length')
            if content_length and int(content_length) > 5 * 1024 * 1024:  # 5MB
                pending_requests.remove(request)
                return

            nonlocal last_activity
            pending_requests.remove(request)
            last_activity = asyncio.get_event_loop().time()

        # logger.debug(f'Request resolved: {request.url} ({content_type})')

        # Attach event listeners
        page.on('request', on_request)
        page.on('response', on_response)

        try:
            # Wait for idle time
            start_time = asyncio.get_event_loop().time()
            while True:
                await asyncio.sleep(0.1)
                now = asyncio.get_event_loop().time()
                if len(pending_requests) == 0 and (
                        now - last_activity) >= self.config.wait_for_network_idle_page_load_time:
                    break
                if now - start_time > self.config.maximum_wait_page_load_time:
                    logger.debug(
                        f'Network timeout after {self.config.maximum_wait_page_load_time}s with {len(pending_requests)} '
                        f'pending requests: {[r.url for r in pending_requests]}'
                    )
                    break

        finally:
            # Clean up event listeners
            page.remove_listener('request', on_request)
            page.remove_listener('response', on_response)

        logger.debug(f'⚖️  Network stabilized for {self.config.wait_for_network_idle_page_load_time} seconds')

    async def _wait_for_page_and_frames_load(self, timeout_overwrite: float | None = None):
        """
        Ensures page is fully loaded before continuing.
        Waits for either network to be idle or minimum WAIT_TIME, whichever is longer.
        Also checks if the loaded URL is allowed.
        """
        # Start timing
        start_time = time.time()

        # Wait for page load
        try:
            await self._wait_for_stable_network()

            # Check if the loaded URL is allowed
            page = await self.get_current_page()
            await self._check_and_handle_navigation(page)
        except URLNotAllowedError as e:
            raise e
        except Exception:
            logger.warning('⚠️  Page load failed, continuing...')
            pass

        # Calculate remaining time to meet minimum WAIT_TIME
        elapsed = time.time() - start_time
        remaining = max((timeout_overwrite or self.config.minimum_wait_page_load_time) - elapsed, 0)

        logger.debug(f'--Page loaded in {elapsed:.2f} seconds, waiting for additional {remaining:.2f} seconds')

        # Sleep remaining time if needed
        if remaining > 0:
            await asyncio.sleep(remaining)

    async def get_selector_map(self) -> SelectorMap:
        session = await self.get_session()
        if session.cached_state is None:
            return {}
        return session.cached_state.selector_map

    def _is_url_allowed(self, url: str) -> bool:
        """Check if a URL is allowed based on the whitelist configuration."""
        if not self.config.allowed_domains:
            return True

        try:
            from urllib.parse import urlparse

            parsed_url = urlparse(url)
            domain = parsed_url.netloc.lower()

            # Special case: Allow 'about:blank' explicitly
            if url == 'about:blank':
                return True

            # Remove port number if present
            if ':' in domain:
                domain = domain.split(':')[0]

            # Check if domain matches any allowed domain pattern
            return any(
                domain == allowed_domain.lower() or domain.endswith('.' + allowed_domain.lower())
                for allowed_domain in self.config.allowed_domains
            )
        except Exception as e:
            logger.error(f'⛔️  Error checking URL allowlist: {str(e)}')
            return False


    async def _check_and_handle_navigation(self) -> None:
        """Check if current page URL is allowed and handle if not."""
        current_url = self.driver.current_url
        if not self._is_url_allowed(current_url):
            logger.warning(f'⛔️  Navigation to non-allowed URL detected: {current_url}')
            try:
                self.go_back()
            except Exception as e:
                logger.error(f'⛔️  Failed to go back after detecting non-allowed URL: {str(e)}')
            raise URLNotAllowedError(f'Navigation to non-allowed URL: {current_url}')

    def _wait_for_page_load(self, timeout=10):
        WebDriverWait(self.driver, timeout).until(
            lambda d: d.execute_script('return document.readyState') == 'complete'
        )

    async def navigate_to(self, url: str):
        if not self._is_url_allowed(url):
            raise BrowserError(f'Navigation to non-allowed URL: {url}')

        self.driver.get(url)
        self._wait_for_page_load()

    async def refresh_page(self):
        """Refresh the current page"""
        self.driver.refresh()
        self._wait_for_page_load()

    async def go_back(self):
        """Navigate back in history"""
        try:
            self.driver.back()
            self._wait_for_page_load(timeout=1)
        except Exception as e:
            logger.debug(f'⏮️  Error during go_back: {e}')

    async def go_forward(self):
        """Navigate forward in history"""
        try:
            self.driver.forward()
            self._wait_for_page_load(timeout=1)
        except Exception as e:
            logger.debug(f'⏭️  Error during go_forward: {e}')

    async def close_current_tab(self):
        """Close the current tab"""
        self.driver.close()
        handles = self.driver.window_handles
        if handles:
            self.driver.switch_to.window(handles[0])
            self.active_tab = Page(self.driver, handles[0], self.driver.current_url)
        else:
            self.active_tab = None

    async def get_page_html(self) -> str:
        """Get the current page HTML content"""
        return self.driver.page_source

    async def execute_javascript(self, script: str):
        """Execute JavaScript code on the page"""
        page = await self.get_current_page()
        return await page.evaluate(script)


    async def get_page_structure(self) -> str:
        """Get a debug view of the page structure including iframes"""
        debug_script = """(() => {
			function getPageStructure(element = document, depth = 0, maxDepth = 10) {
				if (depth >= maxDepth) return '';

				const indent = '  '.repeat(depth);
				let structure = '';

				// Skip certain elements that clutter the output
				const skipTags = new Set(['script', 'style', 'link', 'meta', 'noscript']);

				// Add current element info if it's not the document
				if (element !== document) {
					const tagName = element.tagName.toLowerCase();

					// Skip uninteresting elements
					if (skipTags.has(tagName)) return '';

					const id = element.id ? `#${element.id}` : '';
					const classes = element.className && typeof element.className === 'string' ?
						`.${element.className.split(' ').filter(c => c).join('.')}` : '';

					// Get additional useful attributes
					const attrs = [];
					if (element.getAttribute('role')) attrs.push(`role="${element.getAttribute('role')}"`);
					if (element.getAttribute('aria-label')) attrs.push(`aria-label="${element.getAttribute('aria-label')}"`);
					if (element.getAttribute('type')) attrs.push(`type="${element.getAttribute('type')}"`);
					if (element.getAttribute('name')) attrs.push(`name="${element.getAttribute('name')}"`);
					if (element.getAttribute('src')) {
						const src = element.getAttribute('src');
						attrs.push(`src="${src.substring(0, 50)}${src.length > 50 ? '...' : ''}"`);
					}

					// Add element info
					structure += `${indent}${tagName}${id}${classes}${attrs.length ? ' [' + attrs.join(', ') + ']' : ''}\\n`;

					// Handle iframes specially
					if (tagName === 'iframe') {
						try {
							const iframeDoc = element.contentDocument || element.contentWindow?.document;
							if (iframeDoc) {
								structure += `${indent}  [IFRAME CONTENT]:\\n`;
								structure += getPageStructure(iframeDoc, depth + 2, maxDepth);
							} else {
								structure += `${indent}  [IFRAME: No access - likely cross-origin]\\n`;
							}
						} catch (e) {
							structure += `${indent}  [IFRAME: Access denied - ${e.message}]\\n`;
						}
					}
				}

				// Get all child elements
				const children = element.children || element.childNodes;
				for (const child of children) {
					if (child.nodeType === 1) { // Element nodes only
						structure += getPageStructure(child, depth + 1, maxDepth);
					}
				}

				return structure;
			}

			return getPageStructure();
		})()"""

        page = await self.get_current_page()
        structure = await page.evaluate(debug_script)
        return (structure

    @time_execution_sync('--get_state'))
    async def get_state(self) -> BrowserState:
        """Get the current state of the browser"""
        await self._wait_for_page_and_frames_load()
        session = await self.get_session()
        session.cached_state = await self._update_browser_state()

        # Save cookies if a file is specified
        if self.config.cookies_file:
            asyncio.create_task(self.save_cookies())

        return session.cached_state

    async def _update_browser_state(self, focus_element: int = -1) -> BrowserState:
        """Update and return state."""
        session = await self.get_session()

        # Check if current page is still valid, if not switch to another available page
        try:
            page = await self.get_current_page()
            # Test if page is still accessible
            await page.evaluate('1')
        except Exception as e:
            logger.debug(f'👋  Current page is no longer accessible: {str(e)}')
            # Get all available pages
            pages = session.pages
            if pages:
                self.state.target_id = None
                page = await self._get_current_page(session)
                logger.debug(f'🔄  Switched to page: {await page.title()}')
            else:
                raise BrowserError('Browser closed: no valid pages available')

        try:
            await self.remove_highlights()
            dom_service = DomService(page)
            content = await dom_service.get_clickable_elements(
				focus_element=focus_element,
				viewport_expansion=self.config.viewport_expansion,
				highlight_elements=self.config.highlight_elements,
			)

            tabs_info = await self.get_tabs_info()

            # Get all cross-origin iframes within the page and open them in new tabs
			# mark the titles of the new tabs so the LLM knows to check them for additional content
			# unfortunately too buggy for now, too many sites use invisible cross-origin iframes for ads, tracking, youtube videos, social media, etc.
			# and it distracts the bot by opening a lot of new tabs
			# iframe_urls = await dom_service.get_cross_origin_iframes()
			# for url in iframe_urls:
			# 	if url in [tab.url for tab in tabs_info]:
			# 		continue  # skip if the iframe if we already have it open in a tab
			# 	new_page_id = tabs_info[-1].page_id + 1
			# 	logger.debug(f'Opening cross-origin iframe in new tab #{new_page_id}: {url}')
			# 	await self.create_new_tab(url)
			# 	tabs_info.append(
			# 		TabInfo(
			# 			page_id=new_page_id,
			# 			url=url,
			# 			title=f'iFrame opened as new tab, treat as if embedded inside page #{self.state.target_id}: {page.url}',
			# 			parent_page_id=self.state.target_id,
			# 		)
			# 	)

            screenshot_b64 = await self.take_browser_screenshot()
            pixels_above, pixels_below = await self.get_scroll_info(page)

            self.current_state = BrowserState(
				element_tree=content.element_tree,
				selector_map=content.selector_map,
				url=page.url,
				title=await page.title(),
				tabs=tabs_info,
				screenshot=screenshot_b64,
				pixels_above=pixels_above,
				pixels_below=pixels_below,
			)

            return self.current_state
        except Exception as e:
            logger.error(f'❌  Failed to update state: {str(e)}')
            # Return last known good state if available
            if hasattr(self, 'current_state'):
                return self.current_state
            raise

    # region - Browser Actions
    @time_execution_async('--take_browser_screenshot')
    async def take_browser_screenshot(self, full_page: bool = False) -> str:
        """
        Returns a base64-encoded screenshot of the current page.
        Selenium does not support full-page screenshots natively without workarounds.
        """
        try:
            self.driver.switch_to.window(self.driver.current_window_handle)
            if full_page:
                # Optional full-page workaround using JS scroll + stitch (advanced)
                logger.warning("Full-page screenshots require custom scroll+stitch in Selenium.")
            screenshot_png = self.driver.get_screenshot_as_png()
            screenshot_b64 = base64.b64encode(screenshot_png).decode('utf-8')
            return screenshot_b64
        except Exception as e:
            logger.error(f"Failed to take screenshot: {str(e)}")
            raise


    @time_execution_async('--remove_highlights')
    async def remove_highlights(self):
        """
        Removes all highlight overlays and labels created by the highlightElement function.
        """
        js = """
        try {
            const container = document.getElementById('playwright-highlight-container');
            if (container) container.remove();
    
            const highlightedElements = document.querySelectorAll('[browser-user-highlight-id^="playwright-highlight-"]');
            highlightedElements.forEach(el => {
                el.removeAttribute('browser-user-highlight-id');
            });
        } catch (e) {
            console.error('Failed to remove highlights:', e);
        }
        """
        try:
            self.driver.execute_script(js)
        except Exception as e:
            logger.debug(f'⚠️ Failed to remove highlights (usually ok): {e}')


    # region - User Actions
    @classmethod
    def _convert_simple_xpath_to_css_selector(cls, xpath: str) -> str:
        """Converts simple XPath expressions to CSS selectors."""
        if not xpath:
            return ''

        # Remove leading slash if present
        xpath = xpath.lstrip('/')

        # Split into parts
        parts = xpath.split('/')
        css_parts = []

        for part in parts:
            if not part:
                continue

            # Handle custom elements with colons by escaping them
            if ':' in part and '[' not in part:
                base_part = part.replace(':', r'\:')
                css_parts.append(base_part)
                continue

            # Handle index notation [n]
            if '[' in part:
                base_part = part[: part.find('[')]
                # Handle custom elements with colons in the base part
                if ':' in base_part:
                    base_part = base_part.replace(':', r'\:')
                index_part = part[part.find('[') :]

                # Handle multiple indices
                indices = [i.strip('[]') for i in index_part.split(']')[:-1]]

                for idx in indices:
                    try:
                        # Handle numeric indices
                        if idx.isdigit():
                            index = int(idx) - 1
                            base_part += f':nth-of-type({index + 1})'
                        # Handle last() function
                        elif idx == 'last()':
                            base_part += ':last-of-type'
                        # Handle position() functions
                        elif 'position()' in idx:
                            if '>1' in idx:
                                base_part += ':nth-of-type(n+2)'
                    except ValueError:
                        continue

                css_parts.append(base_part)
            else:
                css_parts.append(part)

        base_selector = ' > '.join(css_parts)
        return base_selector


    @classmethod
    @time_execution_sync('--enhanced_css_selector_for_element')
    def _enhanced_css_selector_for_element(cls, element: DOMElementNode, include_dynamic_attributes: bool = True) -> str:
        """
        Creates a CSS selector for a DOM element, handling various edge cases and special characters.

        Args:
            element: The DOM element to create a selector for

        Returns:
            A valid CSS selector string
        """
        try:
            # Get base selector from XPath
            css_selector = cls._convert_simple_xpath_to_css_selector(element.xpath)

            # Handle class attributes
            if 'class' in element.attributes and element.attributes['class'] and include_dynamic_attributes:
                # Define a regex pattern for valid class names in CSS
                valid_class_name_pattern = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_-]*$')

                # Iterate through the class attribute values
                classes = element.attributes['class'].split()
                for class_name in classes:
                    # Skip empty class names
                    if not class_name.strip():
                        continue

                    # Check if the class name is valid
                    if valid_class_name_pattern.match(class_name):
                        # Append the valid class name to the CSS selector
                        css_selector += f'.{class_name}'
                    else:
                        # Skip invalid class names
                        continue

            # Expanded set of safe attributes that are stable and useful for selection
            SAFE_ATTRIBUTES = {
                # Data attributes (if they're stable in your application)
                'id',
                # Standard HTML attributes
                'name',
                'type',
                'placeholder',
                # Accessibility attributes
                'aria-label',
                'aria-labelledby',
                'aria-describedby',
                'role',
                # Common form attributes
                'for',
                'autocomplete',
                'required',
                'readonly',
                # Media attributes
                'alt',
                'title',
                'src',
                # Custom stable attributes (add any application-specific ones)
                'href',
                'target',
            }

            if include_dynamic_attributes:
                dynamic_attributes = {
                    'data-id',
                    'data-qa',
                    'data-cy',
                    'data-testid',
                }
                SAFE_ATTRIBUTES.update(dynamic_attributes)

            # Handle other attributes
            for attribute, value in element.attributes.items():
                if attribute == 'class':
                    continue

                # Skip invalid attribute names
                if not attribute.strip():
                    continue

                if attribute not in SAFE_ATTRIBUTES:
                    continue

                # Escape special characters in attribute names
                safe_attribute = attribute.replace(':', r'\:')

                # Handle different value cases
                if value == '':
                    css_selector += f'[{safe_attribute}]'
                elif any(char in value for char in '"\'<>`\n\r\t'):
                    # Use contains for values with special characters
                    # Regex-substitute *any* whitespace with a single space, then strip.
                    collapsed_value = re.sub(r'\s+', ' ', value).strip()
                    # Escape embedded double-quotes.
                    safe_value = collapsed_value.replace('"', '\\"')
                    css_selector += f'[{safe_attribute}*="{safe_value}"]'
                else:
                    css_selector += f'[{safe_attribute}="{value}"]'

            return css_selector

        except Exception:
            # Fallback to a more basic selector if something goes wrong
            tag_name = element.tag_name or '*'
            return (f"{tag_name}[highlight_index='{element.highlight_index}']"


    @time_execution_async('--get_locate_element'))
    async def get_locate_element(self, element: DOMElementNode) -> Optional[ElementHandle]:
        """
            Locate an element using a DOMElementNode, handling nested iframes and dynamic selectors.
            Returns a wrapped ElementHandle object (custom wrapper over Selenium WebElement).
            """
        try:
            self.driver.switch_to.default_content()  # Start from main document

            # Step 1: Traverse parents up to root
            parents: list[DOMElementNode] = []
            current = element
            while current.parent is not None:
                parent = current.parent
                parents.append(parent)
                current = parent
            parents.reverse()  # Top to bottom

            # Step 2: Traverse through nested iframes
            for parent in parents:
                if parent.tag_name.lower() == 'iframe':
                    iframe_selector = self._enhanced_css_selector_for_element(
                        parent, include_dynamic_attributes=self.config.include_dynamic_attributes
                    )
                    try:
                        iframe_element = self.driver.find_element(By.CSS_SELECTOR, iframe_selector)
                        self.driver.switch_to.frame(iframe_element)
                    except Exception as e:
                        logger.error(f'❌ Failed to switch into iframe: {e}')
                        return None

            # Step 3: Locate final element in the correct frame
            css_selector = self._enhanced_css_selector_for_element(
                element, include_dynamic_attributes=self.config.include_dynamic_attributes
            )

            selenium_element = self.driver.find_element(By.CSS_SELECTOR, css_selector)
            wrapped = ElementHandle(selenium_element, self.driver)  # Your custom wrapper
            wrapped.scroll_into_view_if_needed()
            return wrapped

        except Exception as e:
            logger.error(f'❌ Failed to locate element: {str(e)}')
            return None

    @time_execution_async('--get_locate_element_by_xpath')
    async def get_locate_element_by_xpath(self, xpath: str):
        """ Locates an element on the page using the provided XPath. """
        try:
            element = self.driver.find_element("xpath", xpath)
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
            return element
        except NoSuchElementException:
            logger.error(f"❌ Failed to locate element by XPath: {xpath}")
            return None

    @time_execution_async('--get_locate_element_by_css_selector')
    async def get_locate_element_by_css_selector(self, css_selector: str):
        """Locates an element on the page using the provided CSS selector."""
        current_frame = await self.get_current_page()

        try:
            element = self.driver.find_element("css selector", css_selector)
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
            return element
        except NoSuchElementException:
            logger.error(f"❌ Failed to locate element by CSS selector: {css_selector}")
            return None


    @time_execution_async('--get_locate_element_by_text')
    async def get_locate_element_by_text(
            self, text: str, nth: Optional[int] = 0, element_type: Optional[str] = None):
        """
		Locates an element on the page using the provided text.
		If `nth` is provided, it returns the nth matching element (0-based).
		If `element_type` is provided, filters by tag name (e.g., 'button', 'span').
		"""

        try:
            tag = element_type or "*"
            xpath = f".//{tag}[contains(normalize-space(), '{text}')]"
            elements = self.driver.find_elements("xpath", xpath)

            # Filter only visible elements
            visible_elements = [el for el in elements if el.is_displayed()]

            if not visible_elements:
                logger.error(f"No visible element with text '{text}' found.")
                return None

            if 0 <= nth < len(visible_elements):
                element = visible_elements[nth]
            else:
                logger.error(f"Visible element with text '{text}' not found at index {nth}.")
                return None

            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
            return element
        except Exception as e:
            logger.error(f"❌ Failed to locate element by text '{text}': {str(e)}")
            return None


    @time_execution_async('--input_text_element_node')
    async def _input_text_element_node(self, element_node: DOMElementNode, text: str):
        try:
            element = self.get_locate_element(element_node)
            if element is None:
                raise BrowserError(f'Element: {repr(element_node)} not found')

            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)

            tag_name = element.tag_name.lower()
            is_contenteditable = element.get_attribute("contenteditable") == "true"
            readonly = element.get_attribute("readonly") is not None
            disabled = element.get_attribute("disabled") is not None

            if (is_contenteditable or tag_name == 'input') and not (readonly or disabled):
                try:
                    self.driver.execute_script("arguments[0].textContent = ''; arguments[0].value = '';", element)
                except Exception:
                    pass
                element.clear()
                element.send_keys(text)
            else:
                # fallback (some elements support .send_keys only)
                element.clear()
                element.send_keys(text)

        except Exception as e:
            logger.debug(f'❌  Failed to input text into element: {repr(element_node)}. Error: {str(e)}')
            raise BrowserError(f'Failed to input text into index {element_node.highlight_index}')

    @time_execution_async('--click_element_node')
    async def _click_element_node(self, element_node: DOMElementNode) -> Optional[str]:
        """
		Optimized method to click an element using xpath.
		"""
        try:
            element = self.get_locate_element(element_node)
            if element is None:
                raise Exception(f'Element: {repr(element_node)} not found')

            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)

            def perform_click():
                prev_url = self.driver.current_url
                element.click()

                # Handle potential navigation
                try:
                    WebDriverWait(self.driver, 5).until(
                        lambda d: d.current_url != prev_url
                    )
                    self._check_and_handle_navigation()
                except TimeoutException:
                    logger.debug("Click did not trigger navigation.")

            if self.config.save_downloads_path:
                # Downloads in Selenium are handled via browser profile (preconfigured)
                perform_click()
                # You must manually check the download folder for new files
                # Add logic here to detect most recent file
                logger.debug("⬇️  Download assumed, check download directory.")
                return None
            else:
                perform_click()
                return None

        except URLNotAllowedError as e:
            raise e
        except Exception as e:
            # Retry with JS click
            try:
                self.driver.execute_script("arguments[0].click();", element)
                return None
            except Exception as inner:
                raise Exception(f'Failed to click element: {repr(element_node)}. Error: {str(inner)}')

    @time_execution_async('--get_tabs_info')
    async def get_tabs_info(self) -> list[TabInfo]:
        tabs_info = []
        original_handle = self.driver.current_window_handle

        for page_id, handle in enumerate(self.driver.window_handles):
            try:
                self.driver.switch_to.window(handle)

                # Title can hang in rare cases (rare in Selenium but simulate it)
                try:
                    WebDriverWait(self.driver, 1).until(
                        lambda d: d.title is not None
                    )
                    title = self.driver.title
                    url = self.driver.current_url
                except TimeoutException:
                    title = 'ignore this tab and do not use it'
                    url = 'about:blank'

                tabs_info.append(TabInfo(page_id=page_id, url=url, title=title))
            except Exception as e:
                logger.debug(f'⚠  Failed to get tab info for tab #{page_id}: {str(e)}')
                tabs_info.append(TabInfo(page_id=page_id, url='about:blank', title='ignore this tab and do not use it'))

        self.driver.switch_to.window(original_handle)
        return tabs_info

    @time_execution_async('--switch_to_tab')
    async def switch_to_tab(self, page_id: int):
        """Switch to a specific tab by its page_id"""
        handles = self.driver.window_handles

        if page_id >= len(handles):
            raise BrowserError(f'No tab found with page_id: {page_id}')

        handle = handles[page_id]
        self.driver.switch_to.window(handle)

        url = self.driver.current_url
        if not self._is_url_allowed(url):
            raise BrowserError(f'Cannot switch to tab with non-allowed URL: {url}')

        self.active_tab = Page(self.driver, handle, url)  # Optional: track it
        self._wait_for_page_load()


    @time_execution_async('--create_new_tab')
    async def create_new_tab(self, url: str | None = None) -> None:
        """Create a new tab and optionally navigate to a URL"""
        if url and not self._is_url_allowed(url):
            raise BrowserError(f'Cannot create new tab with non-allowed URL: {url}')

        original_handle = self.driver.current_window_handle
        existing_handles = self.driver.window_handles

        self.driver.execute_script("window.open('');")
        WebDriverWait(self.driver, 5).until(
            lambda d: len(d.window_handles) > len(existing_handles)
        )

        new_handles = [h for h in self.driver.window_handles if h not in existing_handles]
        if not new_handles:
            raise BrowserError("Failed to open new tab")

        self.driver.switch_to.window(new_handles[0])
        self.active_tab = Page(self.driver, new_handles[0], url)

        if url:
            self.driver.get(url)
            self._wait_for_page_load()

    # region - Helper methods for easier access to the DOM
    async def _get_current_page(self, session: BrowserSession):
        # Try to use active tab if it's still open
        if self.active_tab.handle in self.driver.window_handles:
            self.driver.switch_to.window(self.active_tab.handle)
            return self.active_tab

        # Fallback: find last non-extension page
        for handle in reversed(self.driver.window_handles):
            self.driver.switch_to.window(handle)
            url = self.driver.current_url
            if not url.startswith("chrome-extension://") and not url.startswith("chrome://"):
                self.active_tab = Page(self.driver, handle, url)
                return self.active_tab

        # Still nothing? Open a new tab
        self.create_new_tab()
        return self.active_tab

    async def get_element_by_index(self, index: int) -> ElementHandle | None:
        selector_map = await self.get_selector_map()
        element_handle = await self.get_locate_element(selector_map[index])
        return element_handle

    async def get_dom_element_by_index(self, index: int) -> DOMElementNode:
        selector_map = await self.get_selector_map()
        return selector_map[index]


    async def is_file_downloader(self, element: DOMElementNode, max_depth: int = 3, current_depth: int = 0) -> bool:
        if current_depth > max_depth:
            return False
        if not isinstance(element, DOMElementNode):
            return False

        # Check for anchor tag with a downloadable file
        if element.tag_name == 'a':
            href = element.attributes.get('href', '')
            download_attr = element.attributes.get('download', None)

            # File extensions commonly associated with downloads
            download_extensions = ['.pdf', '.zip', '.exe', '.doc', '.docx', '.xlsx', '.csv', '.tar', '.gz', '.rar', '.gif', '.png', '.jpg', '.jpeg', '.tiff', '.mp4', '.mjpeg']

            if download_attr is not None:
                return True
            if any(href.endswith(ext) for ext in download_extensions):
                return True

        # Optional: Check if onclick handler or data attribute suggests download
        onclick = element.attributes.get('onclick', '') or ''
        if 'download' in onclick.lower():
            return True
        if any('download' in key.lower() for key in element.attributes.keys()):
            return True

        # Recursively check children
        for child in element.children:
            if isinstance(child, DOMElementNode):
                if self.is_file_downloader(child, max_depth, current_depth + 1):
                    return True

        return False

    async def get_scroll_info(self) -> tuple[int, int]:
        """
        Get scroll position information for the current page.
        Returns (pixels_above, pixels_below)
        """
        scroll_y = self.driver.execute_script("return window.scrollY;")
        viewport_height = self.driver.execute_script("return window.innerHeight;")
        total_height = self.driver.execute_script("return document.documentElement.scrollHeight;")

        pixels_above = scroll_y
        pixels_below = total_height - (scroll_y + viewport_height)

        return pixels_above, pixels_below

    async def wait_for_element(self, selector: str, timeout: float) -> None:
        """
        Waits for an element matching the given CSS selector to become visible.

        Args:
            selector (str): The CSS selector of the element.
            timeout (float): The maximum time to wait for the element to be visible (in milliseconds).

        Raises:
            TimeoutError: If the element does not become visible within the specified timeout.
		"""

        page = await self.get_current_page()
        await page.wait_for_selector(selector, state='visible', timeout=timeout)