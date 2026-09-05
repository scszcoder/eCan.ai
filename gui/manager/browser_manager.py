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
from threading import Lock, Timer
from typing import Optional, Dict, List, Any, Tuple, TYPE_CHECKING
from uuid_extensions import uuid7str

from pydantic import BaseModel, Field, ConfigDict

from utils.logger_helper import logger_helper as logger
from utils.logger_helper import get_traceback
from utils import agent_status as _agent_status

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


# =============================================================================
# Browser Slot — abstraction for a Chrome instance slot on a vehicle
# =============================================================================

class BrowserSlot(BaseModel):
    """A configured Chrome instance slot on a machine/vehicle.

    Each slot represents one Chrome process addressable by CDP port.
    Agents are assigned to slots; once a slot reaches ``max_agents`` the
    pool spills over to the next available slot (or launches a new Chrome).

    When no slots are explicitly configured the BrowserManager falls back
    to its legacy ``port_pool`` behaviour (backward-compatible default).
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)

    # Slot identity
    id: str = Field(default="", description="Unique slot id, e.g. 'slot_9228'. Auto-generated from port if blank.")
    cdp_port: int = Field(default=9228, description="CDP port for this Chrome instance")

    # Capacity
    max_agents: int = Field(default=12, description="Max concurrent agents on this Chrome")

    # Chrome profile / data dir
    user_data_dir: Optional[str] = Field(default=None, description="Chrome --user-data-dir. Auto-generated per-port if None.")
    profile: Optional[str] = Field(default=None, description="Browser profile name (maps to Chrome --profile-directory)")

    # Runtime state (not persisted)
    assigned_agents: List[str] = Field(default_factory=list, description="Agent IDs currently assigned to this slot")
    status: str = Field(default="idle", description="idle | active | full | error")
    last_error: Optional[str] = Field(default=None)

    def model_post_init(self, __context: Any) -> None:
        if not self.id:
            self.id = f"slot_{self.cdp_port}"

    @property
    def agent_count(self) -> int:
        return len(self.assigned_agents)

    @property
    def has_capacity(self) -> bool:
        return self.agent_count < self.max_agents

    def assign_agent(self, agent_id: str) -> None:
        if agent_id not in self.assigned_agents:
            self.assigned_agents.append(agent_id)
        self.status = "full" if not self.has_capacity else "active"

    def release_agent(self, agent_id: str) -> None:
        if agent_id in self.assigned_agents:
            self.assigned_agents.remove(agent_id)
        if not self.assigned_agents:
            self.status = "idle"
        elif self.has_capacity:
            self.status = "active"

    def to_state_dict(self) -> dict:
        """Fields to inject into task state so the agent reconnects to this slot."""
        return {
            "browser_slot_id": self.id,
            "cdp_port": str(self.cdp_port),
            "browser_profile": self.profile or "",
        }


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
    
    # Slot assignment (when using browser slot pool)
    slot_id: Optional[str] = Field(default=None, description="BrowserSlot.id this browser belongs to")

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
    Automatically downloads matching ChromeDriver if version mismatch detected.
    
    Args:
        webdriver_path: Path to chromedriver executable
        cdp_address: CDP address (e.g., "127.0.0.1:9228" or full selenium address)
    
    Returns:
        WebDriver instance or None if failed
    """
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from selenium.common.exceptions import InvalidArgumentException, WebDriverException, SessionNotCreatedException
    
    driver = None
    current_webdriver_path = webdriver_path
    
    try:
        chrome_options = Options()
        chrome_options.add_experimental_option("debuggerAddress", cdp_address)
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        
        service = Service(executable_path=current_webdriver_path, log_output=subprocess.DEVNULL)
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
        except SessionNotCreatedException as e:
            # Check if it's a version mismatch error
            error_msg = str(e)
            if "This version of ChromeDriver only supports Chrome version" in error_msg:
                logger.warning(f"[WebDriver] Version mismatch detected: {error_msg}")
                logger.info(f"[WebDriver] Attempting to download matching ChromeDriver...")
                
                # Try to download matching ChromeDriver
                try:
                    from gui.webdriver.utils import detect_chrome_version
                    from gui.webdriver.downloader import WebDriverDownloader
                    from gui.webdriver.config import get_webdriver_dir
                    
                    # Detect Chrome version
                    chrome_version = detect_chrome_version()
                    if chrome_version:
                        logger.info(f"[WebDriver] Detected Chrome version: {chrome_version}")
                        
                        # Download matching ChromeDriver
                        downloader = WebDriverDownloader()
                        webdriver_dir = get_webdriver_dir()
                        
                        # Use a dedicated thread to run the async download, avoiding
                        # "Cannot run the event loop while another loop is running" when
                        # this sync function is called from within an async context.
                        import asyncio
                        import concurrent.futures
                        def _run_download():
                            loop = asyncio.new_event_loop()
                            try:
                                return loop.run_until_complete(
                                    downloader.download_webdriver(chrome_version, webdriver_dir)
                                )
                            finally:
                                loop.close()
                        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                            future = executor.submit(_run_download)
                            new_driver_path = future.result(timeout=120)
                        
                        if new_driver_path:
                            logger.info(f"[WebDriver] ✅ Downloaded matching ChromeDriver: {new_driver_path}")
                            current_webdriver_path = new_driver_path
                            
                            # Retry with new ChromeDriver
                            service = Service(executable_path=current_webdriver_path, log_output=subprocess.DEVNULL)
                            if sys.platform == "win32":
                                try:
                                    service.creationflags = _get_windows_creation_flags()
                                except Exception:
                                    pass
                            
                            driver = webdriver.Chrome(service=service, options=chrome_options)
                            logger.info(f"[WebDriver] ✅ Successfully connected with new ChromeDriver")
                        else:
                            logger.error(f"[WebDriver] Failed to download matching ChromeDriver")
                            raise
                    else:
                        logger.error(f"[WebDriver] Could not detect Chrome version")
                        raise
                        
                except Exception as download_error:
                    logger.error(f"[WebDriver] Auto-download failed: {download_error}")
                    raise e  # Re-raise original error
            else:
                raise  # Re-raise if not a version mismatch error
        
        # Inject stealth script
        if driver:
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


def _create_browser_session_for_cdp(cdp_url: str, session_id_prefix: str = "br", downloads_path: Optional[str] = None, profile_name: Optional[str] = None) -> Any:
    """
    Create a browser_use BrowserSession connected to existing Chrome via CDP.
    
    Args:
        cdp_url: Full CDP URL (e.g., "http://127.0.0.1:9228")
        session_id_prefix: Prefix for session ID
        downloads_path: Path for browser downloads (optional)
        profile_name: Browser profile name to use (optional)
    
    Returns:
        BrowserSession instance
    """
    from browser_use import BrowserSession
    from browser_use.browser.profile import BrowserProfile
    
    # Try to load profile settings from backend if profile_name is provided
    profile_settings = {}
    if profile_name:
        try:
            from gui.ipc.w2p_handlers.browser_use_handler import get_profile_by_name
            profile_settings = get_profile_by_name(profile_name) or {}
            logger.debug(f"[BrowserManager] Loaded profile settings for '{profile_name}': {list(profile_settings.keys())}")
        except Exception as e:
            logger.warning(f"[BrowserManager] Failed to load profile settings: {e}")
    
    # Build BrowserProfile with settings.
    # IMPORTANT: runtime cdp_url (from BrowserManager/create_browser) must take precedence.
    # Profile-level cdp_url can be stale (e.g. previous ephemeral debug port) and cause
    # connection refused / BrowserStart timeout.
    configured_cdp_url = profile_settings.get('cdp_url')
    effective_cdp_url = cdp_url or configured_cdp_url
    if configured_cdp_url and cdp_url and configured_cdp_url != cdp_url:
        logger.warning(
            f"[BrowserManager] Ignoring stale profile cdp_url={configured_cdp_url}; using runtime cdp_url={cdp_url}"
        )

    profile_kwargs = {
        'headless': profile_settings.get('headless', False),
        'cdp_url': effective_cdp_url,
    }
    
    # Apply profile settings if available
    # Auto-assign a persistent user_data_dir so login state (cookies, sessions) survives restarts
    if profile_settings.get('user_data_dir'):
        profile_kwargs['user_data_dir'] = profile_settings['user_data_dir']
    else:
        # Use current user's data directory for browser profiles
        from utils.user_path_helper import ensure_user_data_dir
        _profile_id = profile_settings.get('id') or profile_settings.get('name') or profile_name or 'default'
        import re as _re
        _safe_id = _re.sub(r'[^\w\-]', '_', str(_profile_id))
        _auto_dir = ensure_user_data_dir(subdir=os.path.join('browser_profiles', _safe_id))
        profile_kwargs['user_data_dir'] = _auto_dir
        logger.info(f"[BrowserManager] Auto-assigned user_data_dir for profile '{_profile_id}': {_auto_dir}")
    if profile_settings.get('user_agent'):
        profile_kwargs['user_agent'] = profile_settings['user_agent']
    if profile_settings.get('viewport_width') and profile_settings.get('viewport_height'):
        profile_kwargs['viewport'] = {
            'width': profile_settings['viewport_width'],
            'height': profile_settings['viewport_height']
        }
    if profile_settings.get('args'):
        profile_kwargs['args'] = profile_settings['args']
    if profile_settings.get('disable_security'):
        profile_kwargs['disable_security'] = profile_settings['disable_security']
    if profile_settings.get('deterministic_rendering'):
        profile_kwargs['deterministic_rendering'] = profile_settings['deterministic_rendering']
    
    # Domain restrictions
    if profile_settings.get('allowed_domains'):
        profile_kwargs['allowed_domains'] = profile_settings['allowed_domains']
    if profile_settings.get('prohibited_domains'):
        profile_kwargs['prohibited_domains'] = profile_settings['prohibited_domains']
    if profile_settings.get('block_ip_addresses'):
        profile_kwargs['block_ip_addresses'] = profile_settings['block_ip_addresses']
    
    # Session settings
    if profile_settings.get('keep_alive') is not None:
        profile_kwargs['keep_alive'] = profile_settings['keep_alive']
    if profile_settings.get('enable_default_extensions') is not None:
        profile_kwargs['enable_default_extensions'] = profile_settings['enable_default_extensions']
    if profile_settings.get('demo_mode'):
        profile_kwargs['demo_mode'] = profile_settings['demo_mode']
    if profile_settings.get('cookie_whitelist_domains'):
        profile_kwargs['cookie_whitelist_domains'] = profile_settings['cookie_whitelist_domains']
    
    # Window settings
    if profile_settings.get('window_width') and profile_settings.get('window_height'):
        profile_kwargs['window_size'] = {
            'width': profile_settings['window_width'],
            'height': profile_settings['window_height']
        }
    if profile_settings.get('window_position_x') is not None and profile_settings.get('window_position_y') is not None:
        profile_kwargs['window_position'] = {
            'width': profile_settings['window_position_x'],
            'height': profile_settings['window_position_y']
        }
    
    # iFrame settings
    if profile_settings.get('cross_origin_iframes') is not None:
        profile_kwargs['cross_origin_iframes'] = profile_settings['cross_origin_iframes']
    if profile_settings.get('max_iframes'):
        profile_kwargs['max_iframes'] = profile_settings['max_iframes']
    if profile_settings.get('max_iframe_depth'):
        profile_kwargs['max_iframe_depth'] = profile_settings['max_iframe_depth']
    
    # Timing settings
    if profile_settings.get('minimum_wait_page_load_time') is not None:
        profile_kwargs['minimum_wait_page_load_time'] = profile_settings['minimum_wait_page_load_time']
    if profile_settings.get('wait_for_network_idle_page_load_time') is not None:
        profile_kwargs['wait_for_network_idle_page_load_time'] = profile_settings['wait_for_network_idle_page_load_time']
    if profile_settings.get('wait_between_actions') is not None:
        profile_kwargs['wait_between_actions'] = profile_settings['wait_between_actions']
    
    # UI/DOM settings
    if profile_settings.get('highlight_elements') is not None:
        profile_kwargs['highlight_elements'] = profile_settings['highlight_elements']
    if profile_settings.get('dom_highlight_elements') is not None:
        profile_kwargs['dom_highlight_elements'] = profile_settings['dom_highlight_elements']
    if profile_settings.get('filter_highlight_ids') is not None:
        profile_kwargs['filter_highlight_ids'] = profile_settings['filter_highlight_ids']
    if profile_settings.get('paint_order_filtering') is not None:
        profile_kwargs['paint_order_filtering'] = profile_settings['paint_order_filtering']
    if profile_settings.get('interaction_highlight_color'):
        profile_kwargs['interaction_highlight_color'] = profile_settings['interaction_highlight_color']
    if profile_settings.get('interaction_highlight_duration') is not None:
        profile_kwargs['interaction_highlight_duration'] = profile_settings['interaction_highlight_duration']
    
    # Downloads
    if profile_settings.get('auto_download_pdfs') is not None:
        profile_kwargs['auto_download_pdfs'] = profile_settings['auto_download_pdfs']
    
    # Recording
    if profile_settings.get('record_video_dir'):
        profile_kwargs['record_video_dir'] = profile_settings['record_video_dir']
    if profile_settings.get('record_video_framerate'):
        profile_kwargs['record_video_framerate'] = profile_settings['record_video_framerate']
    
    profile = BrowserProfile(**profile_kwargs)
    profile.is_local = profile_settings.get('is_local', False)
    profile.use_cloud = profile_settings.get('use_cloud', False)
    
    # Override downloads_path if provided as parameter
    if downloads_path:
        profile.downloads_path = downloads_path
    elif profile_settings.get('downloads_path'):
        profile.downloads_path = profile_settings['downloads_path']
    
    # Set profile_directory
    if profile_settings.get('profile_directory'):
        profile.profile_directory = profile_settings['profile_directory']
    elif profile_name:
        profile.profile_directory = profile_name
    
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
    
    # Default port pool and capacity for auto-scaling browser instances.
    DEFAULT_PORT_POOL = list(range(9228, 9238))  # ports 9228-9237 (10 slots)
    DEFAULT_MAX_AGENTS_PER_BROWSER = 12

    def __init__(
        self,
        default_webdriver_path: Optional[str] = None,
        port_pool: Optional[List[int]] = None,
        max_agents_per_browser: int = 0,
        slots: Optional[List[Dict[str, Any]]] = None,
    ):
        """
        Initialize BrowserManager.

        Args:
            default_webdriver_path: Default path to chromedriver executable
            port_pool: List of CDP ports available for auto-scaling Chrome instances.
                       When an agent requests cdp_port=0 (auto), the manager picks
                       the least-loaded port from this pool, spawning a new Chrome
                       instance if the current ones are at capacity.
                       Ignored when ``slots`` is provided.
            max_agents_per_browser: Max concurrent agents per Chrome instance.
                                   0 means use DEFAULT_MAX_AGENTS_PER_BROWSER.
                                   Ignored when ``slots`` is provided.
            slots: Optional list of BrowserSlot dicts. When provided, these define
                   the available Chrome instances explicitly (port, capacity,
                   user_data_dir, profile). Overrides port_pool/max_agents_per_browser.
                   Example::

                       [
                           {"cdp_port": 9228, "max_agents": 15, "user_data_dir": "C:\\chrome_data"},
                           {"cdp_port": 9229, "max_agents": 15, "profile": "slot2"},
                       ]
        """
        self._lock = Lock()
        self._browsers: Dict[str, AutoBrowser] = {}
        self._default_webdriver_path = default_webdriver_path

        # Slot-based pool (explicit configuration)
        self._slots: Dict[str, BrowserSlot] = {}

        # Idle browser auto-shutdown configuration
        # When a browser is released (mark_idle), a delayed shutdown is scheduled.
        # If the browser is re-acquired before the delay, the shutdown is cancelled.
        self._idle_shutdown_delay: float = float(
            os.environ.get("ECAN_BROWSER_IDLE_SHUTDOWN_DELAY", "60")
        )  # seconds; 0 = disabled
        self._pending_shutdowns: Dict[str, Timer] = {}  # browser_id -> Timer

        if slots:
            self.configure_slots(slots)
            # Derive legacy fields from slots for backward compat
            self._port_pool = [s.cdp_port for s in self._slots.values()]
            self._max_agents_per_browser = max(
                (s.max_agents for s in self._slots.values()),
                default=self.DEFAULT_MAX_AGENTS_PER_BROWSER,
            )
        else:
            self._port_pool: List[int] = port_pool or list(self.DEFAULT_PORT_POOL)
            self._max_agents_per_browser: int = max_agents_per_browser or self.DEFAULT_MAX_AGENTS_PER_BROWSER

        logger.info(
            f"BrowserManager initialized ("
            f"slots={len(self._slots) or 'none (legacy pool)'}, "
            f"port_pool={self._port_pool}, "
            f"max_agents_per_browser={self._max_agents_per_browser})"
        )
    
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

    # -----------------------------------------------------------------
    # Browser Slot management
    # -----------------------------------------------------------------

    def configure_slots(self, slot_dicts: List[Dict[str, Any]]) -> None:
        """Configure browser slots from a list of dicts (e.g. vehicle settings).

        Existing slot runtime state (assigned_agents) is preserved when
        reconfiguring a slot that already exists with the same id.
        """
        with self._lock:
            for sd in slot_dicts or []:
                slot = BrowserSlot(**sd)
                existing = self._slots.get(slot.id)
                if existing:
                    # Preserve runtime assignments, update config fields
                    slot.assigned_agents = list(existing.assigned_agents)
                    slot.status = existing.status
                self._slots[slot.id] = slot
            logger.info(f"[BrowserSlot] Configured {len(self._slots)} slot(s): "
                        f"{[s.id for s in self._slots.values()]}")

    def get_slot(self, slot_id: str) -> Optional[BrowserSlot]:
        """Get a slot by ID."""
        return self._slots.get(slot_id)

    def get_slot_by_port(self, cdp_port: int) -> Optional[BrowserSlot]:
        """Get the slot assigned to a given CDP port."""
        for slot in self._slots.values():
            if slot.cdp_port == cdp_port:
                return slot
        return None

    def get_all_slots(self) -> List[BrowserSlot]:
        """Return all configured slots."""
        return list(self._slots.values())

    @property
    def has_slots(self) -> bool:
        """True if explicit slots are configured (vs legacy port-pool mode)."""
        return bool(self._slots)

    def get_slots_summary(self) -> List[dict]:
        """Status summary of all slots, useful for dashboards / logging."""
        return [
            {
                "id": s.id,
                "cdp_port": s.cdp_port,
                "max_agents": s.max_agents,
                "agent_count": s.agent_count,
                "has_capacity": s.has_capacity,
                "status": s.status,
                "assigned_agents": list(s.assigned_agents),
                "profile": s.profile,
                "user_data_dir": s.user_data_dir,
            }
            for s in self._slots.values()
        ]

    # -----------------------------------------------------------------
    # Browser pool: auto-scaling across slots or legacy port set
    # -----------------------------------------------------------------

    def count_agents_on_port(self, cdp_port: int) -> int:
        """Count how many agents (IN_USE browsers) are on a given CDP port."""
        # Prefer slot tracking when available
        slot = self.get_slot_by_port(cdp_port)
        if slot:
            return slot.agent_count
        with self._lock:
            return sum(
                1 for b in self._browsers.values()
                if b.cdp_port == cdp_port and b.status == BrowserStatus.IN_USE
            )

    def get_port_load_map(self) -> Dict[int, int]:
        """Return {port: active_agent_count} for every port that has browsers."""
        if self._slots:
            return {s.cdp_port: s.agent_count for s in self._slots.values()}
        with self._lock:
            load: Dict[int, int] = {}
            for b in self._browsers.values():
                if b.status == BrowserStatus.IN_USE:
                    load[b.cdp_port] = load.get(b.cdp_port, 0) + 1
            return load

    def pick_auto_slot(self, agent_id: str = "") -> Optional[BrowserSlot]:
        """Pick the best slot for a new agent.

        Returns the slot with the most remaining capacity.  If the agent
        is already assigned to a slot, returns that slot (sticky).

        Only available when explicit slots are configured; returns None
        otherwise (caller should fall back to ``pick_auto_port``).
        """
        if not self._slots:
            return None

        # Sticky: if agent already assigned, return that slot
        if agent_id:
            for slot in self._slots.values():
                if agent_id in slot.assigned_agents:
                    logger.debug(f"[BrowserSlot] Agent {agent_id} sticky to slot {slot.id}")
                    return slot

        # Pick least-loaded slot with capacity
        best: Optional[BrowserSlot] = None
        for slot in self._slots.values():
            if not slot.has_capacity:
                continue
            if best is None or slot.agent_count < best.agent_count:
                best = slot

        if best:
            logger.info(
                f"[BrowserSlot] Auto-selected slot {best.id} "
                f"(port={best.cdp_port}, load={best.agent_count}/{best.max_agents})"
            )
        else:
            logger.warning("[BrowserSlot] All slots at capacity, cannot auto-assign")
        return best

    def pick_auto_port(self, agent_id: str = "") -> Optional[int]:
        """Pick the best CDP port from the pool for a new agent.

        When explicit slots are configured, delegates to ``pick_auto_slot``.
        Otherwise falls back to legacy port-pool scanning.

        Strategy (legacy):
          1. Prefer a port that already has a running Chrome with room to spare.
          2. If all running instances are at capacity, pick the first unused port
             from the pool (a new Chrome will be launched on it).
          3. If the entire pool is exhausted, return None.
        """
        # Slot-based path
        slot = self.pick_auto_slot(agent_id=agent_id)
        if slot is not None:
            return slot.cdp_port
        if self._slots:
            # Slots configured but all full
            return None

        # Legacy port-pool path
        load_map = self.get_port_load_map()

        # Also count idle browsers — the Chrome process is running even if idle
        with self._lock:
            active_ports = {b.cdp_port for b in self._browsers.values()
                           if b.status in (BrowserStatus.IN_USE, BrowserStatus.IDLE)}

        # Phase 1: find a running Chrome with room
        best_port = None
        best_load = self._max_agents_per_browser + 1
        for port in self._port_pool:
            if port in active_ports:
                current_load = load_map.get(port, 0)
                if current_load < self._max_agents_per_browser and current_load < best_load:
                    best_port = port
                    best_load = current_load

        if best_port is not None:
            logger.info(
                f"[BrowserPool] Auto-selected port {best_port} "
                f"(load={load_map.get(best_port, 0)}/{self._max_agents_per_browser})"
            )
            return best_port

        # Phase 2: pick first unused port — will trigger Chrome auto-start
        from gui.unified_browser_manager import _is_port_in_use
        for port in self._port_pool:
            if port not in active_ports:
                # Double-check the port isn't occupied by an external process
                if not _is_port_in_use(port):
                    logger.info(
                        f"[BrowserPool] All active browsers at capacity. "
                        f"Spawning new Chrome on port {port}"
                    )
                    return port
                else:
                    # Port occupied externally; treat it as available Chrome
                    logger.info(
                        f"[BrowserPool] Port {port} in use externally (existing Chrome?), "
                        f"selecting it for new agent"
                    )
                    return port

        logger.warning(
            f"[BrowserPool] All {len(self._port_pool)} ports at capacity "
            f"(max {self._max_agents_per_browser} agents each). Cannot auto-assign."
        )
        return None

    def find_available_browser(
        self,
        browser_type: Optional[BrowserType] = None,
        cdp_port: Optional[int] = None,
        adspower_profile_id: Optional[str] = None,
        profile: Optional[str] = None,
    ) -> Optional[AutoBrowser]:
        """
        Find an available browser matching the criteria.
        
        Matching rules:
        - AdsPower: Only 1 instance per machine, so just match type (ignore port/profile)
        - Chrome/Chromium: Match type and port; if profile is requested,
          require profile consistency as well
        
        Args:
            browser_type: Required browser type (chrome, adspower, chromium)
            cdp_port: Specific CDP port to match (ignored for adspower)
            adspower_profile_id: Specific AdsPower profile to match (ignored - only 1 instance)
            profile: Browser profile name to match for Chrome/Chromium (optional)
            
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

                # If caller requested a specific profile, only reuse a browser
                # with the same profile to avoid cross-profile login-state leakage.
                if profile:
                    existing_profile = str(browser.profile or "")
                    requested_profile = str(profile)
                    if existing_profile != requested_profile:
                        continue
                
                return browser
        
        return None

    def find_browser_for_owner(
        self,
        agent_id: str,
        task: Optional[str] = None,
        browser_type: Optional[BrowserType] = None,
        cdp_port: Optional[int] = None,
        profile: Optional[str] = None,
    ) -> Optional[AutoBrowser]:
        """
        Find a browser already marked IN_USE by the same scoped owner.

        This is needed for long-lived browser-use nodes that may re-enter after
        cache churn. Reusing the exact same owned browser avoids creating a new
        BrowserSession for the same chat/control scope.
        """
        if not agent_id:
            return None

        with self._lock:
            for browser in self._browsers.values():
                if browser.status != BrowserStatus.IN_USE:
                    continue
                if str(browser.current_agent_id or "") != str(agent_id):
                    continue
                if task is not None and str(browser.current_task or "") != str(task):
                    continue
                if browser_type and browser.browser_type != browser_type:
                    continue
                if cdp_port and browser.cdp_port != cdp_port:
                    continue
                if profile:
                    existing_profile = str(browser.profile or "")
                    requested_profile = str(profile)
                    if existing_profile != requested_profile:
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
        slot_id: Optional[str] = None,
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

                chrome_user_data_dir = None
                chrome_profile_directory = None
                if profile:
                    try:
                        from gui.ipc.w2p_handlers.browser_use_handler import get_profile_by_name
                        from utils.user_path_helper import ensure_user_data_dir
                        import re as _re

                        profile_settings = get_profile_by_name(profile) or {}
                        if profile_settings.get('user_data_dir'):
                            chrome_user_data_dir = profile_settings['user_data_dir']
                        else:
                            _profile_id = profile_settings.get('id') or profile_settings.get('name') or profile or 'default'
                            _safe_id = _re.sub(r'[^\w\-]', '_', str(_profile_id))
                            chrome_user_data_dir = ensure_user_data_dir(subdir=os.path.join('browser_profiles', _safe_id))

                        chrome_profile_directory = profile_settings.get('profile_directory') or 'Default'
                    except Exception as e:
                        logger.warning(f"[BrowserManager] Failed to resolve persistent Chrome profile settings: {e}")
                
                # If a slot specifies user_data_dir, use it for Chrome launch
                if not chrome_user_data_dir and slot_id:
                    _slot = self.get_slot(slot_id)
                    if _slot and _slot.user_data_dir:
                        chrome_user_data_dir = _slot.user_data_dir
                        logger.info(f"[BrowserManager] Using slot user_data_dir: {chrome_user_data_dir}")

                # Auto-start Chrome if not running
                from gui.unified_browser_manager import _is_port_in_use, _start_chrome_with_cdp
                _chrome_auto_started = False
                if not _is_port_in_use(final_cdp_port):
                    logger.info(f"[BrowserManager] Chrome not detected on port {final_cdp_port}, auto-starting...")
                    _chrome_auto_started = True
                    _agent_status.report(chrome="auto_starting", chrome_port=final_cdp_port)
                    headless = False  # Default to non-headless for better debugging
                    if not _start_chrome_with_cdp(
                        final_cdp_port,
                        headless,
                        user_data_dir=chrome_user_data_dir,
                        profile_directory=chrome_profile_directory,
                    ):
                        logger.warning(f"[BrowserManager] Failed to auto-start Chrome on port {final_cdp_port}")
                        _agent_status.report(chrome="unreachable", chrome_port=final_cdp_port)
                        logger.warning(f"[BrowserManager] Please manually start Chrome with: chrome --remote-debugging-port={final_cdp_port}")
                    else:
                        logger.info(f"[BrowserManager] ✅ Chrome auto-started successfully on port {final_cdp_port}")
                        _agent_status.report(chrome="auto_started", chrome_port=final_cdp_port)
                
                # For webdriver, we need just the address without protocol
                selenium_address = f"127.0.0.1:{cdp_port}"
                
                logger.info(f"[BrowserManager] Connecting to existing {browser_type.value} at {final_cdp_url}")
                if not _chrome_auto_started:
                    _agent_status.report(chrome="attached_existing", chrome_port=final_cdp_port)

                # Preflight: warn (never block) if we're about to drive a blank
                # debug Chrome while the customer's real Chrome is a separate,
                # invisible window (the two-Chrome trap).
                try:
                    from gui.unified_browser_manager import preflight_chrome_conflict
                    preflight_chrome_conflict(final_cdp_port, auto_started=_chrome_auto_started)
                except Exception as _pf_exc:
                    logger.debug(f"[BrowserManager] preflight_chrome_conflict skipped: {_pf_exc}")
            
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
            elif not connect_webdriver:
                logger.info(
                    f"[BrowserManager] Skipping WebDriver connection "
                    f"for {final_cdp_url} (connect_webdriver=False)"
                )
            
            # =================================================================
            # Create BrowserSession connection
            # =================================================================
            if connect_browser_session and final_cdp_url:
                session_prefix = "ap" if browser_type == BrowserType.ADSPOWER else "ec"
                logger.debug(f"[BrowserManager] Creating BrowserSession for {final_cdp_url}")
                session = _create_browser_session_for_cdp(final_cdp_url, session_prefix, downloads_path=downloads_path, profile_name=profile)
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
                    slot_id=slot_id,
                    status=BrowserStatus.IDLE if (driver or session) else BrowserStatus.ERROR,
                )

                self._browsers[browser.id] = browser
                logger.info(
                    f"[BrowserManager] Created browser: {browser.id} "
                    f"(type={browser_type.value}, cdp={final_cdp_url}"
                    f"{f', slot={slot_id}' if slot_id else ''})"
                )
            
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
        profile: Optional[str] = None,
        connect_webdriver: bool = True,
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
            profile: Browser profile name to use (optional, for browser_use BrowserProfile)
            
        Returns:
            Acquired AutoBrowser instance or None
        """
        # cdp_port=0 means "auto-assign from pool/slot"
        _assigned_slot: Optional[BrowserSlot] = None
        if cdp_port == 0:
            auto_port = self.pick_auto_port(agent_id=agent_id)
            if auto_port is None:
                logger.error(
                    f"[BrowserManager] Agent {agent_id} requested auto port but pool is exhausted"
                )
                return None
            effective_cdp_port = auto_port
            _assigned_slot = self.get_slot_by_port(effective_cdp_port)
            logger.info(
                f"[BrowserManager] Auto-assigned cdp_port={effective_cdp_port} for agent {agent_id}"
                f"{f' (slot={_assigned_slot.id})' if _assigned_slot else ''}"
            )
        else:
            effective_cdp_port = cdp_port or 9228
            # Even with explicit port, resolve the slot if one exists
            _assigned_slot = self.get_slot_by_port(effective_cdp_port)

        # First, try to reuse a browser already owned by this exact scoped
        # agent/task. This prevents duplicate BrowserSession creation when the
        # caller loses its local cache but the BrowserManager still owns the
        # correct in-use browser for the same scope.
        browser = self.find_browser_for_owner(
            agent_id=agent_id,
            task=task,
            browser_type=browser_type,
            cdp_port=effective_cdp_port,
            profile=profile,
        )
        if browser:
            # Cancel any pending idle shutdown so the browser isn't killed mid-reuse
            self.cancel_pending_shutdown(browser.id)
            logger.info(
                f"[BrowserManager] Agent {agent_id} reusing owned browser {browser.id} "
                f"(task={task or ''}, profile={profile or browser.profile}, cdp_port={effective_cdp_port})"
            )
            return browser

        # Try to find an available browser
        browser = self.find_available_browser(
            browser_type=browser_type,
            cdp_port=effective_cdp_port,
            adspower_profile_id=adspower_profile_id,
            profile=profile,
        )

        if browser:
            # Cancel any pending idle shutdown so the browser isn't killed mid-reuse
            self.cancel_pending_shutdown(browser.id)

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
            browser.slot_id = _assigned_slot.id if _assigned_slot else None
            if _assigned_slot:
                _assigned_slot.assign_agent(agent_id)
            logger.info(
                f"[BrowserManager] Agent {agent_id} acquired existing browser {browser.id} "
                f"(profile={profile or browser.profile}, cdp_port={effective_cdp_port}"
                f"{f', slot={_assigned_slot.id}' if _assigned_slot else ''})"
            )
            return browser

        # Create new browser if allowed
        if create_if_not_found:
            # When slot specifies user_data_dir, pass it as profile hint
            _slot_profile = profile
            if not _slot_profile and _assigned_slot and _assigned_slot.profile:
                _slot_profile = _assigned_slot.profile

            browser = self.create_browser(
                browser_type=browser_type or BrowserType.CHROME,
                cdp_port=effective_cdp_port,
                adspower_profile_id=adspower_profile_id,
                adspower_api_key=adspower_api_key,
                webdriver_path=webdriver_path,
                downloads_path=downloads_path,
                profile=_slot_profile,
                slot_id=_assigned_slot.id if _assigned_slot else None,
                connect_webdriver=connect_webdriver,
            )

            # Only mark in use if browser was created successfully
            if browser.status != BrowserStatus.ERROR:
                browser.mark_in_use(agent_id, task)
                if _assigned_slot:
                    _assigned_slot.assign_agent(agent_id)
                logger.info(
                    f"[BrowserManager] Agent {agent_id} created and acquired new browser {browser.id} "
                    f"(profile={_slot_profile or browser.profile}, cdp_port={effective_cdp_port}"
                    f"{f', slot={_assigned_slot.id}' if _assigned_slot else ''})"
                )
            else:
                logger.error(f"[BrowserManager] Agent {agent_id} failed to create browser: {browser.last_error}")
            
            return browser
        
        logger.warning(f"[BrowserManager] Agent {agent_id} could not acquire a browser")
        return None
    
    def release_browser(self, browser_id: str) -> bool:
        """
        Release a browser back to the pool.

        If ``idle_shutdown_delay`` > 0, schedules a delayed shutdown so the Chrome
        process is killed if the browser isn't re-acquired within that window.
        This prevents Chrome instances from accumulating indefinitely.

        Args:
            browser_id: ID of the browser to release

        Returns:
            True if released successfully, False if browser not found
        """
        with self._lock:
            browser = self._browsers.get(browser_id)
            if not browser:
                return False

            # Release agent from slot tracking
            if browser.slot_id and browser.current_agent_id:
                slot = self._slots.get(browser.slot_id)
                if slot:
                    slot.release_agent(browser.current_agent_id)

            browser.mark_idle()

            # Cancel any pending shutdown that was previously scheduled
            pending = self._pending_shutdowns.pop(browser_id, None)
            if pending:
                pending.cancel()

            # Schedule auto-shutdown after idle timeout
            if self._idle_shutdown_delay > 0:
                self._schedule_delayed_shutdown(browser_id, self._idle_shutdown_delay)

            logger.info(
                f"Released browser: {browser_id}"
                f"{f', auto-shutdown in {self._idle_shutdown_delay}s' if self._idle_shutdown_delay > 0 else ''}"
            )
            return True

    def _schedule_delayed_shutdown(self, browser_id: str, delay: float) -> None:
        """
        Schedule a delayed shutdown for a browser that has been idle.

        The shutdown is a best-effort asyncio call. If the event loop is not
        running, falls back to a synchronous quit on the webdriver.
        """
        # Cancel any previously scheduled shutdown for this browser
        existing = self._pending_shutdowns.get(browser_id)
        if existing:
            existing.cancel()

        def _do_shutdown():
            # Pop the timer ref first
            self._pending_shutdowns.pop(browser_id, None)

            browser = self._browsers.get(browser_id)
            if browser is None:
                logger.debug(f"[IdleShutdown] Browser {browser_id} already removed")
                return

            # Only shutdown if still idle (wasn't re-acquired)
            if browser.status != BrowserStatus.IDLE:
                logger.debug(f"[IdleShutdown] Browser {browser_id} is no longer idle (status={browser.status.value}), skipping shutdown")
                return

            logger.info(f"[IdleShutdown] Browser {browser_id} idle timeout reached — shutting down Chrome (cdp_port={browser.cdp_port})")
            try:
                # Try graceful async shutdown first
                try:
                    loop = asyncio.get_running_loop()
                    # Schedule on the running loop so we don't block
                    loop.call_soon(lambda: asyncio.create_task(self.shutdown_browser(browser_id, force=True)))
                    return
                except RuntimeError:
                    # No running loop — fall back to synchronous quit
                    pass

                if browser.browser_session:
                    try:
                        # browser_use BrowserSession.close() is async; best-effort
                        loop = asyncio.new_event_loop()
                        loop.run_until_complete(browser.browser_session.close())
                        loop.close()
                    except Exception as e:
                        logger.warning(f"[IdleShutdown] Error closing browser_session for {browser_id}: {e}")

                if browser.webdriver:
                    try:
                        browser.webdriver.quit()
                        logger.info(f"[IdleShutdown] WebDriver.quit() successful for {browser_id}")
                    except Exception as e:
                        logger.warning(f"[IdleShutdown] Error quitting webdriver for {browser_id}: {e}")

                # Remove from registry
                with self._lock:
                    if browser_id in self._browsers:
                        del self._browsers[browser_id]
                logger.info(f"[IdleShutdown] Browser {browser_id} removed from registry")
            except Exception as e:
                logger.error(f"[IdleShutdown] Unexpected error shutting down browser {browser_id}: {e}")

        timer = Timer(delay, _do_shutdown, name=f"IdleShutdown_{browser_id}")
        timer.daemon = True
        timer.start()
        self._pending_shutdowns[browser_id] = timer
        logger.debug(f"[IdleShutdown] Scheduled shutdown for {browser_id} in {delay}s")

    def cancel_pending_shutdown(self, browser_id: str) -> None:
        """Cancel any pending idle shutdown for a browser (e.g. when it is re-acquired)."""
        pending = self._pending_shutdowns.pop(browser_id, None)
        if pending:
            pending.cancel()
            logger.debug(f"[IdleShutdown] Cancelled pending shutdown for {browser_id}")
    
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
        finally:
            # Cancel any pending idle shutdown to avoid double-cleanup
            self.cancel_pending_shutdown(browser_id)
    
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
            
            summary = {
                "total": len(self._browsers),
                "status_counts": status_counts,
                "browsers": [
                    {
                        "id": b.id,
                        "type": b.browser_type.value,
                        "status": b.status.value,
                        "cdp_port": b.cdp_port,
                        "slot_id": b.slot_id,
                        "current_agent": b.current_agent_id,
                        "current_task": b.current_task,
                        "last_used": b.last_used_at.isoformat() if b.last_used_at else None,
                    }
                    for b in self._browsers.values()
                ],
            }
            if self._slots:
                summary["slots"] = self.get_slots_summary()
            return summary
