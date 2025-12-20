#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Browser Manager - Manages multiple browser instances for automation tasks
"""

import os
import sys
import subprocess
import asyncio
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, List, Any, Tuple, TYPE_CHECKING
from threading import Lock
from uuid_extensions import uuid7str

from pydantic import BaseModel, Field, ConfigDict

from utils.logger_helper import logger_helper as logger
from utils.logger_helper import get_traceback

if TYPE_CHECKING:
    from browser_use import BrowserSession
    from selenium.webdriver.remote.webdriver import WebDriver


class BrowserType(str, Enum):
    """Supported browser types"""
    CHROME = "chrome"
    ADSPOWER = "adspower"
    CHROMIUM = "chromium"
    # Future expansion
    # FIREFOX = "firefox"
    # EDGE = "edge"


class BrowserStatus(str, Enum):
    """Browser instance status"""
    IDLE = "idle"              # Available for use
    IN_USE = "in_use"          # Currently being used by an agent
    STARTING = "starting"      # Being launched
    STOPPING = "stopping"      # Being shut down
    ERROR = "error"            # In error state
    DISCONNECTED = "disconnected"  # Lost connection


class AutoBrowser(BaseModel):
    """
    Represents a single browser instance managed by BrowserManager.
    
    This class wraps browser_use's BrowserSession along with metadata
    needed for managing multiple browser instances.
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    # Unique identifier for this browser instance
    id: str = Field(default_factory=lambda: f"ab_{uuid7str()}")
    
    # Browser type (chrome, adspower, chromium)
    browser_type: BrowserType = BrowserType.CHROME
    
    # browser_use BrowserSession instance
    browser_session: Optional[Any] = Field(default=None, description="browser_use BrowserSession instance")
    
    # Selenium WebDriver instance (for direct selenium operations)
    webdriver: Optional[Any] = Field(default=None, description="Selenium WebDriver instance")
    
    # Browser profile information (JSON string or dict)
    profile: Optional[Any] = Field(default=None, description="Browser profile configuration")
    
    # CDP (Chrome DevTools Protocol) port
    cdp_port: int = Field(default=9228, description="Chrome DevTools Protocol port")
    
    # CDP URL for connection
    cdp_url: Optional[str] = Field(default=None, description="Full CDP URL for connection")
    
    # Path to webdriver executable
    webdriver_path: Optional[str] = Field(default=None, description="Path to chromedriver executable")
    
    # Current status
    status: BrowserStatus = Field(default=BrowserStatus.IDLE)
    
    # ID of the agent currently using this browser (if any)
    current_agent_id: Optional[str] = Field(default=None)
    
    # Task/job description currently being performed
    current_task: Optional[str] = Field(default=None)
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.now)
    last_used_at: Optional[datetime] = Field(default=None)
    
    # AdsPower specific fields
    adspower_profile_id: Optional[str] = Field(default=None, description="AdsPower profile ID")
    
    # Error information
    last_error: Optional[str] = Field(default=None)
    
    def is_available(self) -> bool:
        """Check if this browser is available for use"""
        return self.status == BrowserStatus.IDLE
    
    def is_connected(self) -> bool:
        """Check if browser session is connected"""
        if self.browser_session is None:
            return False
        # Could add more sophisticated connection checking here
        return self.status not in [BrowserStatus.ERROR, BrowserStatus.DISCONNECTED, BrowserStatus.STOPPING]
    
    def mark_in_use(self, agent_id: str, task: Optional[str] = None):
        """Mark this browser as being used by an agent"""
        self.status = BrowserStatus.IN_USE
        self.current_agent_id = agent_id
        self.current_task = task
        self.last_used_at = datetime.now()
    
    def mark_idle(self):
        """Mark this browser as idle/available"""
        self.status = BrowserStatus.IDLE
        self.current_agent_id = None
        self.current_task = None
        self.last_used_at = datetime.now()
    
    def mark_error(self, error_msg: str):
        """Mark this browser as in error state"""
        self.status = BrowserStatus.ERROR
        self.last_error = error_msg
        self.current_agent_id = None
        self.current_task = None


# =============================================================================
# Helper functions for browser creation
# =============================================================================

def _get_windows_creation_flags():
    """Get Windows-specific process creation flags to hide console window."""
    if sys.platform == "win32":
        return subprocess.CREATE_NO_WINDOW
    return 0


def _create_webdriver_for_cdp(webdriver_path: str, cdp_address: str) -> Any:
    """
    Create a Selenium WebDriver connected to an existing Chrome via CDP.
    
    Args:
        webdriver_path: Path to chromedriver executable
        cdp_address: CDP address (e.g., "127.0.0.1:9228" or full selenium address)
    
    Returns:
        WebDriver instance or None if failed
    """
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from selenium.common.exceptions import InvalidArgumentException, WebDriverException
    
    driver = None
    try:
        chrome_options = Options()
        chrome_options.add_experimental_option("debuggerAddress", cdp_address)
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        
        service = Service(executable_path=webdriver_path, log_output=subprocess.DEVNULL)
        if sys.platform == "win32":
            try:
                service.creationflags = _get_windows_creation_flags()
            except Exception:
                pass
        
        try:
            driver = webdriver.Chrome(service=service, options=chrome_options)
        except InvalidArgumentException as e:
            logger.warning(f"Chromedriver rejected options, retrying minimal: {e}")
            chrome_options_fallback = Options()
            chrome_options_fallback.add_experimental_option("debuggerAddress", cdp_address)
            driver = webdriver.Chrome(service=service, options=chrome_options_fallback)
        
        # Inject stealth script
        try:
            driver.execute_cdp_cmd(
                "Page.addScriptToEvaluateOnNewDocument",
                {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => false})"}
            )
        except WebDriverException:
            pass
        
        logger.info(f"[WebDriver] Connected to CDP at {cdp_address}")
        
    except Exception as e:
        logger.error(f"[WebDriver] Failed to connect: {e}")
        driver = None
    
    return driver


def _create_browser_session_for_cdp(cdp_url: str, session_id_prefix: str = "br", downloads_path: Optional[str] = None) -> Any:
    """
    Create a browser_use BrowserSession connected to existing Chrome via CDP.
    
    Args:
        cdp_url: Full CDP URL (e.g., "http://127.0.0.1:9228")
        session_id_prefix: Prefix for session ID
        downloads_path: Path for browser downloads (optional)
    
    Returns:
        BrowserSession instance
    """
    from browser_use import BrowserSession
    from browser_use.browser.profile import BrowserProfile
    
    profile = BrowserProfile(headless=False, cdp_url=cdp_url)
    profile.is_local = False
    if downloads_path:
        profile.downloads_path = downloads_path
    return BrowserSession(browser_profile=profile, id=f"{session_id_prefix}_{uuid7str()}")


def _launch_adspower_and_get_cdp(
    api_key: str,
    profile_id: str,
    api_port: int = 50325
) -> Tuple[Optional[str], Optional[str], Optional[int], Optional[str]]:
    """
    Launch AdsPower browser profile and get CDP connection info.
    
    Args:
        api_key: AdsPower API key
        profile_id: AdsPower profile ID
        api_port: AdsPower API port (default: 50325)
    
    Returns:
        Tuple of (cdp_url, selenium_address, debug_port, webdriver_path)
    """
    from agent.mcp.server.ads_power.ads_power import startAdspowerProfile
    
    response = startAdspowerProfile(api_key, profile_id, api_port)
    data = response.get("data", {}) if isinstance(response, dict) else {}
    
    if not data:
        msg = response.get("msg", "Unknown error")
        raise RuntimeError(f"AdsPower failed to start profile: {msg}")
    
    ws_info = data.get("ws", {}) if isinstance(data, dict) else {}
    
    # Extract connection info
    devtools_ws = ws_info.get("devtools") or ws_info.get("chromedevtools")
    selenium_addr = ws_info.get("selenium") or ws_info.get("webdriver")
    debug_port = data.get("debug_port")
    webdriver_path = data.get("webdriver")
    
    # Determine CDP URL
    cdp_url: Optional[str] = None
    if isinstance(devtools_ws, str) and devtools_ws:
        cdp_url = devtools_ws
    elif isinstance(selenium_addr, str) and selenium_addr:
        addr = selenium_addr.replace("ws://", "http://", 1)
        if not (addr.startswith("http://") or addr.startswith("https://")):
            addr = f"http://{addr}"
        cdp_url = addr
    elif debug_port:
        cdp_url = f"http://127.0.0.1:{debug_port}"
    
    if not cdp_url:
        raise RuntimeError("Failed to determine AdsPower CDP endpoint")
    
    logger.info(f"[AdsPower] Launched profile {profile_id}, CDP: {cdp_url}")
    
    return cdp_url, selenium_addr, debug_port, webdriver_path


class BrowserManager:
    """
    Manages multiple AutoBrowser instances.
    
    Provides functionality to:
    - Launch new browser instances
    - Find available browser instances
    - Shutdown browser instances
    - Track browser usage across agents
    """
    
    def __init__(self, default_webdriver_path: Optional[str] = None):
        """
        Initialize BrowserManager.
        
        Args:
            default_webdriver_path: Default path to chromedriver executable
        """
        self._lock = Lock()
        self._browsers: Dict[str, AutoBrowser] = {}
        self._default_webdriver_path = default_webdriver_path
        
        logger.info("BrowserManager initialized")
    
    @property
    def browsers(self) -> Dict[str, AutoBrowser]:
        """Get all managed browsers"""
        return self._browsers.copy()
    
    @property
    def available_browsers(self) -> List[AutoBrowser]:
        """Get list of available (idle) browsers"""
        return [b for b in self._browsers.values() if b.is_available()]
    
    @property
    def active_browsers(self) -> List[AutoBrowser]:
        """Get list of browsers currently in use"""
        return [b for b in self._browsers.values() if b.status == BrowserStatus.IN_USE]
    
    def get_browser(self, browser_id: str) -> Optional[AutoBrowser]:
        """Get a browser by its ID"""
        return self._browsers.get(browser_id)
    
    def find_available_browser(
        self,
        browser_type: Optional[BrowserType] = None,
        cdp_port: Optional[int] = None,
        adspower_profile_id: Optional[str] = None
    ) -> Optional[AutoBrowser]:
        """
        Find an available browser matching the criteria.
        
        Matching rules:
        - AdsPower: Only 1 instance per machine, so just match type (ignore port/profile)
        - Chrome/Chromium: Match type and port (profile not required)
        
        Args:
            browser_type: Required browser type (chrome, adspower, chromium)
            cdp_port: Specific CDP port to match (ignored for adspower)
            adspower_profile_id: Specific AdsPower profile to match (ignored - only 1 instance)
            
        Returns:
            An available AutoBrowser instance or None if not found
        """
        with self._lock:
            for browser in self._browsers.values():
                if not browser.is_available():
                    continue
                
                # Match browser type if specified
                if browser_type and browser.browser_type != browser_type:
                    continue
                
                # AdsPower: Only 1 instance per machine, no need to check port/profile
                if browser_type == BrowserType.ADSPOWER:
                    return browser
                
                # Chrome/Chromium: Match CDP port if specified (profile not required)
                if cdp_port and browser.cdp_port != cdp_port:
                    continue
                
                return browser
        
        return None
    
    def register_browser(self, browser: AutoBrowser) -> str:
        """
        Register an existing AutoBrowser instance.
        
        Args:
            browser: AutoBrowser instance to register
            
        Returns:
            Browser ID
        """
        with self._lock:
            self._browsers[browser.id] = browser
            logger.info(f"Registered browser: {browser.id} (type={browser.browser_type}, port={browser.cdp_port})")
            return browser.id
    
    def create_browser(
        self,
        browser_type: BrowserType = BrowserType.CHROME,
        cdp_port: int = 9228,
        cdp_url: Optional[str] = None,
        webdriver_path: Optional[str] = None,
        profile: Optional[str] = None,
        adspower_profile_id: Optional[str] = None,
        adspower_api_key: Optional[str] = None,
        adspower_api_port: int = 50325,
        connect_webdriver: bool = True,
        connect_browser_session: bool = True,
        downloads_path: Optional[str] = None,
    ) -> AutoBrowser:
        """
        Create and register a new AutoBrowser instance with both WebDriver and BrowserSession.
        
        For Chrome/Chromium: Connects to existing browser via CDP port.
        For AdsPower: Launches profile via AdsPower API, then connects via CDP.
        
        Args:
            browser_type: Type of browser (chrome, chromium, adspower)
            cdp_port: CDP port number (for chrome/chromium)
            cdp_url: Full CDP URL (overrides port)
            webdriver_path: Path to chromedriver executable
            profile: Browser profile configuration (JSON string)
            adspower_profile_id: AdsPower profile ID (required for adspower type)
            adspower_api_key: AdsPower API key (defaults to env ADSPOWER_API_KEY)
            adspower_api_port: AdsPower API port (defaults to env or 50325)
            connect_webdriver: Whether to create WebDriver connection
            connect_browser_session: Whether to create BrowserSession connection
            downloads_path: Path for browser downloads (optional)
            
        Returns:
            Created AutoBrowser instance with both drivers hooked up
        """
        browser = None
        driver = None
        session = None
        final_cdp_url = cdp_url
        final_cdp_port = cdp_port
        final_webdriver_path = webdriver_path or self._default_webdriver_path
        selenium_address = None
        
        try:
            # =================================================================
            # AdsPower: Launch profile first to get CDP endpoint
            # =================================================================
            if browser_type == BrowserType.ADSPOWER:
                if not adspower_profile_id:
                    raise ValueError("adspower_profile_id is required for AdsPower browser type")
                
                # Get API key from param or environment
                api_key = adspower_api_key or os.getenv("ADSPOWER_API_KEY")
                if not api_key:
                    raise ValueError("AdsPower API key not provided (set ADSPOWER_API_KEY env or pass adspower_api_key)")
                
                # Get API port from param or environment
                api_port = adspower_api_port
                if not adspower_api_port:
                    api_port = int(os.getenv("ADSPOWER_PORT", "50325"))
                
                logger.info(f"[BrowserManager] Launching AdsPower profile: {adspower_profile_id}")
                
                # Launch AdsPower and get connection info
                final_cdp_url, selenium_address, debug_port, ads_webdriver_path = _launch_adspower_and_get_cdp(
                    api_key=api_key,
                    profile_id=adspower_profile_id,
                    api_port=api_port
                )
                
                # Use AdsPower-provided webdriver if available
                if ads_webdriver_path and not final_webdriver_path:
                    final_webdriver_path = ads_webdriver_path
                
                if debug_port:
                    final_cdp_port = debug_port
            
            # =================================================================
            # Chrome/Chromium: Use provided CDP URL or construct from port
            # =================================================================
            else:
                if not final_cdp_url:
                    final_cdp_url = f"http://127.0.0.1:{cdp_port}"
                    final_cdp_port = cdp_port
                
                # For webdriver, we need just the address without protocol
                selenium_address = f"127.0.0.1:{cdp_port}"
                
                logger.info(f"[BrowserManager] Connecting to existing {browser_type.value} at {final_cdp_url}")
            
            # =================================================================
            # Create WebDriver connection
            # =================================================================
            if connect_webdriver and final_webdriver_path:
                # Determine the address for webdriver (without http://)
                if selenium_address:
                    wd_address = selenium_address
                elif final_cdp_url:
                    # Strip protocol from CDP URL for webdriver
                    wd_address = final_cdp_url.replace("http://", "").replace("https://", "").replace("ws://", "")
                else:
                    wd_address = f"127.0.0.1:{final_cdp_port}"
                
                logger.debug(f"[BrowserManager] Creating WebDriver for {wd_address}")
                driver = _create_webdriver_for_cdp(final_webdriver_path, wd_address)
                
                if driver:
                    logger.info(f"[BrowserManager] WebDriver connected successfully")
                else:
                    logger.warning(f"[BrowserManager] WebDriver connection failed")
            
            # =================================================================
            # Create BrowserSession connection
            # =================================================================
            if connect_browser_session and final_cdp_url:
                session_prefix = "ap" if browser_type == BrowserType.ADSPOWER else "ec"
                logger.debug(f"[BrowserManager] Creating BrowserSession for {final_cdp_url}")
                session = _create_browser_session_for_cdp(final_cdp_url, session_prefix, downloads_path=downloads_path)
                logger.info(f"[BrowserManager] BrowserSession created: {session.id}")
            
            # =================================================================
            # Create AutoBrowser instance
            # =================================================================
            with self._lock:
                browser = AutoBrowser(
                    browser_type=browser_type,
                    cdp_port=final_cdp_port,
                    cdp_url=final_cdp_url,
                    webdriver_path=final_webdriver_path,
                    profile=profile,
                    adspower_profile_id=adspower_profile_id,
                    browser_session=session,
                    webdriver=driver,
                    status=BrowserStatus.IDLE if (driver or session) else BrowserStatus.ERROR,
                )
                
                self._browsers[browser.id] = browser
                logger.info(f"[BrowserManager] Created browser: {browser.id} (type={browser_type.value}, cdp={final_cdp_url})")
            
        except Exception as e:
            err_trace = get_traceback(e, "BrowserManager.create_browser")
            logger.error(f"[BrowserManager] Failed to create browser: {err_trace}")
            
            # Create browser in error state
            with self._lock:
                browser = AutoBrowser(
                    browser_type=browser_type,
                    cdp_port=final_cdp_port,
                    cdp_url=final_cdp_url,
                    webdriver_path=final_webdriver_path,
                    profile=profile,
                    adspower_profile_id=adspower_profile_id,
                    status=BrowserStatus.ERROR,
                    last_error=str(e),
                )
                self._browsers[browser.id] = browser
        
        return browser
    
    def acquire_browser(
        self,
        agent_id: str,
        task: Optional[str] = None,
        browser_type: Optional[BrowserType] = None,
        cdp_port: Optional[int] = None,
        adspower_profile_id: Optional[str] = None,
        adspower_api_key: Optional[str] = None,
        webdriver_path: Optional[str] = None,
        create_if_not_found: bool = True,
        downloads_path: Optional[str] = None,
    ) -> Optional[AutoBrowser]:
        """
        Acquire a browser for an agent's use.
        
        First tries to find an available browser matching criteria.
        If not found and create_if_not_found is True, creates a new one.
        
        Args:
            agent_id: ID of the agent requesting the browser
            task: Description of the task to be performed
            browser_type: Required browser type
            cdp_port: Required CDP port
            adspower_profile_id: Required AdsPower profile
            adspower_api_key: AdsPower API key (for creating new AdsPower browsers)
            webdriver_path: Path to chromedriver (for creating new browsers)
            create_if_not_found: Whether to create a new browser if none available
            downloads_path: Path for browser downloads (optional, updates existing browser profile if found)
            
        Returns:
            Acquired AutoBrowser instance or None
        """
        # Try to find an available browser
        browser = self.find_available_browser(
            browser_type=browser_type,
            cdp_port=cdp_port,
            adspower_profile_id=adspower_profile_id
        )
        
        if browser:
            # Update downloads_path on existing browser's profile if provided
            if downloads_path and browser.browser_session:
                try:
                    if hasattr(browser.browser_session, 'browser_profile') and browser.browser_session.browser_profile:
                        browser.browser_session.browser_profile.downloads_path = downloads_path
                        browser.browser_session.browser_profile.auto_download_pdfs = True
                        logger.debug(f"[BrowserManager] Updated downloads_path on existing browser {browser.id}")
                except Exception as e:
                    logger.warning(f"[BrowserManager] Failed to update downloads_path on browser {browser.id}: {e}")
            browser.mark_in_use(agent_id, task)
            logger.info(f"[BrowserManager] Agent {agent_id} acquired existing browser {browser.id}")
            return browser
        
        # Create new browser if allowed
        if create_if_not_found:
            browser = self.create_browser(
                browser_type=browser_type or BrowserType.CHROME,
                cdp_port=cdp_port or 9228,
                adspower_profile_id=adspower_profile_id,
                adspower_api_key=adspower_api_key,
                webdriver_path=webdriver_path,
                downloads_path=downloads_path,
            )
            
            # Only mark in use if browser was created successfully
            if browser.status != BrowserStatus.ERROR:
                browser.mark_in_use(agent_id, task)
                logger.info(f"[BrowserManager] Agent {agent_id} created and acquired new browser {browser.id}")
            else:
                logger.error(f"[BrowserManager] Agent {agent_id} failed to create browser: {browser.last_error}")
            
            return browser
        
        logger.warning(f"[BrowserManager] Agent {agent_id} could not acquire a browser")
        return None
    
    def release_browser(self, browser_id: str) -> bool:
        """
        Release a browser back to the pool.
        
        Args:
            browser_id: ID of the browser to release
            
        Returns:
            True if released successfully, False if browser not found
        """
        with self._lock:
            browser = self._browsers.get(browser_id)
            if browser:
                browser.mark_idle()
                logger.info(f"Released browser: {browser_id}")
                return True
            return False
    
    def update_browser_session(self, browser_id: str, browser_session: Any) -> bool:
        """
        Update the browser_session for a browser.
        
        Args:
            browser_id: ID of the browser
            browser_session: New BrowserSession instance
            
        Returns:
            True if updated successfully
        """
        with self._lock:
            browser = self._browsers.get(browser_id)
            if browser:
                browser.browser_session = browser_session
                if browser.status == BrowserStatus.STARTING:
                    browser.status = BrowserStatus.IDLE
                logger.debug(f"Updated browser_session for: {browser_id}")
                return True
            return False
    
    def update_webdriver(self, browser_id: str, webdriver: Any) -> bool:
        """
        Update the webdriver for a browser.
        
        Args:
            browser_id: ID of the browser
            webdriver: New WebDriver instance
            
        Returns:
            True if updated successfully
        """
        with self._lock:
            browser = self._browsers.get(browser_id)
            if browser:
                browser.webdriver = webdriver
                logger.debug(f"Updated webdriver for: {browser_id}")
                return True
            return False
    
    async def shutdown_browser(self, browser_id: str, force: bool = False) -> bool:
        """
        Shutdown a browser instance.
        
        Args:
            browser_id: ID of the browser to shutdown
            force: Force shutdown even if browser is in use
            
        Returns:
            True if shutdown successfully
        """
        with self._lock:
            browser = self._browsers.get(browser_id)
            if not browser:
                return False
            
            if browser.status == BrowserStatus.IN_USE and not force:
                logger.warning(f"Cannot shutdown browser {browser_id}: currently in use by {browser.current_agent_id}")
                return False
            
            browser.status = BrowserStatus.STOPPING
        
        try:
            # Close browser_session if exists
            if browser.browser_session:
                try:
                    await browser.browser_session.close()
                except Exception as e:
                    logger.warning(f"Error closing browser_session for {browser_id}: {e}")
            
            # Close webdriver if exists
            if browser.webdriver:
                try:
                    browser.webdriver.quit()
                except Exception as e:
                    logger.warning(f"Error closing webdriver for {browser_id}: {e}")
            
            # Remove from registry
            with self._lock:
                del self._browsers[browser_id]
            
            logger.info(f"Shutdown browser: {browser_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error shutting down browser {browser_id}: {e}")
            browser.mark_error(str(e))
            return False
    
    async def shutdown_all(self, force: bool = False) -> int:
        """
        Shutdown all browser instances.
        
        Args:
            force: Force shutdown even if browsers are in use
            
        Returns:
            Number of browsers successfully shutdown
        """
        browser_ids = list(self._browsers.keys())
        shutdown_count = 0
        
        for browser_id in browser_ids:
            if await self.shutdown_browser(browser_id, force=force):
                shutdown_count += 1
        
        logger.info(f"Shutdown {shutdown_count}/{len(browser_ids)} browsers")
        return shutdown_count
    
    def get_status_summary(self) -> Dict[str, Any]:
        """
        Get a summary of all browser statuses.
        
        Returns:
            Dictionary with status counts and details
        """
        with self._lock:
            status_counts = {}
            for status in BrowserStatus:
                status_counts[status.value] = sum(1 for b in self._browsers.values() if b.status == status)
            
            return {
                "total": len(self._browsers),
                "status_counts": status_counts,
                "browsers": [
                    {
                        "id": b.id,
                        "type": b.browser_type.value,
                        "status": b.status.value,
                        "cdp_port": b.cdp_port,
                        "current_agent": b.current_agent_id,
                        "current_task": b.current_task,
                        "last_used": b.last_used_at.isoformat() if b.last_used_at else None,
                    }
                    for b in self._browsers.values()
                ]
            }
