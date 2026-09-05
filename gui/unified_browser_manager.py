#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unified Browser Resource Manager
Resolves resource conflicts between crawl4ai, browser_use, and Playwright
"""

from typing import Optional, Any, Dict, TYPE_CHECKING
import sys
import os
import asyncio
from threading import Lock
from functools import wraps

from agent.playwright import get_playwright_manager
from utils.logger_helper import get_traceback
from utils.logger_helper import logger_helper as logger
from agent.ec_skills.llm_utils.llm_utils import run_async_in_worker_thread
from agent.agent_service import get_agent_by_id
from dotenv import load_dotenv
from uuid_extensions import uuid7str

if TYPE_CHECKING:
    from crawl4ai import AsyncWebCrawler
    from browser_use import Agent, BrowserSession
    from browser_use.filesystem.file_system import FileSystem

from browser_use import Agent, BrowserSession
from browser_use.browser.profile import BrowserProfile
from browser_use.llm.openai.chat import ChatOpenAI
from browser_use.browser.session import DEFAULT_BROWSER_PROFILE
try:
    from ..mcp.server.ads_power.ads_power import startAdspowerProfile
except ImportError:
    import sys
    from pathlib import Path

    project_root = Path(__file__).resolve().parents[3]
    if str(project_root) not in sys.path:
        sys.path.append(str(project_root))

    from agent.mcp.server.ads_power.ads_power import startAdspowerProfile


class LoggingChatOpenAI(ChatOpenAI):
    def __init__(self, *args, **kwargs):
        """Initialize with all parent class parameters."""
        super().__init__(*args, **kwargs)
    
    def get_client(self):
        client = super().get_client()
        original_create = client.chat.completions.create

        @wraps(original_create)
        async def create_with_logging(*args, **kwargs):
            response = await original_create(*args, **kwargs)
            org = None

            try:
                org = response.response.headers.get("openai-organization")
            except AttributeError:
                pass

            if org:
                self.logger.info("OpenAI organization: %s", org)

            return response

        client.chat.completions.create = create_with_logging
        return client

load_dotenv()

# Global Chrome process tracker (supports multiple instances)
_chrome_process = None
_chrome_port = None
_chrome_processes: Dict[int, Any] = {}  # port -> Popen, tracks all launched instances


def _is_port_in_use(port: int) -> bool:
    """Check if a port is already in use."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.connect(('127.0.0.1', port))
            return True
        except (ConnectionRefusedError, OSError):
            return False


# ── External CDP host (Electron / Chromium-shell apps) ──────────────────────
# ``ECAN_CDP_HOST_EXE=<full path | installed-app display name>``: instead of
# Google Chrome, launch THAT executable with ``--remote-debugging-port=<port>``
# and attach to it.  Electron apps (a vendor's desktop workbench that embeds
# the same web pages we automate) honour the Chromium switch unless the vendor
# strips it.  Only the debugging switch is passed — no --user-data-dir /
# --profile-directory — so the app keeps its own login state.  Default OFF.
_CDP_HOST_EXE_ENV = "ECAN_CDP_HOST_EXE"
_CDP_HOST_BOOT_WAIT_S = 30  # Electron apps boot slower than bare Chrome


def _resolve_cdp_host_exe() -> Optional[str]:
    """Executable named by ``ECAN_CDP_HOST_EXE``, or None when unset."""
    spec = os.getenv(_CDP_HOST_EXE_ENV, "").strip().strip('"')
    if not spec:
        return None
    if os.path.isfile(spec):
        return spec
    import platform
    if platform.system() != "Windows":
        logger.warning(
            f"[CDP-HOST] {_CDP_HOST_EXE_ENV}={spec!r} is not a file; "
            f"name lookup is Windows-only"
        )
        return None
    hit = _find_installed_app_exe(spec)
    if hit:
        logger.info(f"[CDP-HOST] resolved {spec!r} -> {hit}")
    else:
        logger.error(
            f"[CDP-HOST] no installed app matches {spec!r}; set "
            f"{_CDP_HOST_EXE_ENV} to the full .exe path"
        )
    return hit


def _find_installed_app_exe(name: str) -> Optional[str]:
    """Windows: main .exe of an installed app whose Uninstall DisplayName or
    install folder contains *name* (case-insensitive)."""
    import glob
    import winreg

    needle = name.lower()
    roots = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]
    for root, sub in roots:
        try:
            with winreg.OpenKey(root, sub) as k:
                for i in range(winreg.QueryInfoKey(k)[0]):
                    try:
                        with winreg.OpenKey(k, winreg.EnumKey(k, i)) as app:
                            def _val(n: str) -> str:
                                try:
                                    return str(winreg.QueryValueEx(app, n)[0])
                                except OSError:
                                    return ""
                            if needle not in _val("DisplayName").lower():
                                continue
                            icon = _val("DisplayIcon").split(",")[0].strip().strip('"')
                            if icon.lower().endswith(".exe") and os.path.isfile(icon):
                                return icon
                            loc = _val("InstallLocation").strip().strip('"')
                            for exe in (sorted(glob.glob(os.path.join(loc, "*.exe"))) if loc else []):
                                if "uninst" not in os.path.basename(exe).lower():
                                    return exe
                    except OSError:
                        continue
        except OSError:
            continue
    for base in (
        os.path.expandvars(r"%LOCALAPPDATA%\Programs"),
        os.path.expandvars(r"%LOCALAPPDATA%"),
        os.path.expandvars(r"%PROGRAMFILES%"),
        os.path.expandvars(r"%PROGRAMFILES(X86)%"),
    ):
        for exe in sorted(glob.glob(os.path.join(base, f"*{name}*", "*.exe"))):
            if "uninst" not in os.path.basename(exe).lower():
                return exe
    return None


def _log_cdp_targets(port: int) -> None:
    """Spike telemetry: what the host app exposes over CDP.  The target URLs
    decide whether our page_url_patterns / site hooks can match at all."""
    import json
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=3) as r:
            ver = json.loads(r.read().decode("utf-8"))
        logger.info(f"[CDP-HOST] browser={ver.get('Browser')!r} ua={ver.get('User-Agent')!r}")
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=3) as r:
            targets = json.loads(r.read().decode("utf-8"))
        for t in targets:
            logger.info(
                f"[CDP-HOST] target type={t.get('type')} url={t.get('url')!r} "
                f"title={t.get('title')!r}"
            )
        logger.info(f"[CDP-HOST] {len(targets)} targets on port {port}")
    except Exception as e:
        logger.warning(f"[CDP-HOST] target listing on port {port} failed: {e}")


def _kill_running_host_app(exe: str, port: int) -> None:
    """Electron apps hold a single-instance lock: a second launch merely
    focuses the running one and drops our switch, so the running instance
    has to go before we relaunch it with CDP."""
    import psutil
    name = os.path.basename(exe).lower()
    victims = [p for p in psutil.process_iter(["name"])
               if (p.info.get("name") or "").lower() == name]
    if not victims:
        return
    logger.warning(
        f"[CDP-HOST] {name} already running without CDP ({len(victims)} procs) — "
        f"terminating so it can relaunch with --remote-debugging-port={port}"
    )
    for p in victims:
        try:
            p.kill()
        except psutil.Error:
            pass
    psutil.wait_procs(victims, timeout=8)


def _start_cdp_host_app(exe: str, port: int) -> bool:
    """Launch *exe* with the CDP switch and wait for the port. Returns True
    when the port opened; logs WHY when it did not (the spike's verdict)."""
    import subprocess
    import threading
    import time

    name = os.path.basename(exe)
    try:
        _kill_running_host_app(exe, port)
    except Exception as e:
        logger.warning(f"[CDP-HOST] running-instance check failed: {e}")

    args = [exe, f"--remote-debugging-port={port}"]
    logger.info(f"[CDP-HOST] launching {args}")
    try:
        proc = subprocess.Popen(
            args,
            cwd=os.path.dirname(exe) or None,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception as e:
        logger.error(f"[CDP-HOST] failed to launch {exe}: {e}")
        return False
    _chrome_processes[port] = proc

    for _ in range(_CDP_HOST_BOOT_WAIT_S * 2):
        if _is_port_in_use(port):
            logger.info(f"[CDP-HOST] {name} up with CDP on port {port}")
            _log_cdp_targets(port)
            # Electron shells load their real content well after the port
            # opens; a second snapshot shows what the agent will actually see.
            threading.Timer(20.0, _log_cdp_targets, args=(port,)).start()
            return True
        if proc.poll() is not None:
            logger.error(
                f"[CDP-HOST] VERDICT: {name} exited (code {proc.returncode}) before "
                f"CDP port {port} opened — the app rejects --remote-debugging-port"
            )
            return False
        time.sleep(0.5)
    logger.error(
        f"[CDP-HOST] VERDICT: {name} is running but CDP port {port} never opened "
        f"in {_CDP_HOST_BOOT_WAIT_S}s — the app ignores --remote-debugging-port"
    )
    return False


def _start_chrome_with_cdp(
    port: int = 9228,
    headless: bool = False,
    user_data_dir: str | None = None,
    profile_directory: str | None = None,
) -> bool:
    """
    Start Chrome with remote debugging enabled.
    
    Args:
        port: CDP port number
        headless: Whether to run in headless mode
        user_data_dir: Persistent Chrome user data directory
        profile_directory: Chrome profile directory name (e.g. Default)
        
    Returns:
        True if Chrome started successfully, False otherwise
    """
    global _chrome_process, _chrome_port
    
    # Check if Chrome is already running on this port
    if _is_port_in_use(port):
        logger.info(f"[BrowserManager] Chrome already running on port {port}")
        return True

    host_exe = _resolve_cdp_host_exe()
    if host_exe:
        return _start_cdp_host_app(host_exe, port)

    import subprocess
    import platform
    import time
    
    # Determine Chrome executable path
    system = platform.system()
    chrome_path = None
    
    if system == "Darwin":  # macOS
        chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    elif system == "Windows":
        # Try multiple possible Chrome installation locations on Windows
        possible_paths = [
            "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
            "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
            os.path.expandvars("%LOCALAPPDATA%\\Google\\Chrome\\Application\\chrome.exe"),
            os.path.expandvars("%PROGRAMFILES%\\Google\\Chrome\\Application\\chrome.exe"),
            os.path.expandvars("%PROGRAMFILES(X86)%\\Google\\Chrome\\Application\\chrome.exe"),
        ]
        for path in possible_paths:
            if os.path.exists(path):
                chrome_path = path
                break
    else:  # Linux
        possible_paths = [
            "/usr/bin/google-chrome",
            "/usr/bin/chromium-browser",
            "/usr/bin/chromium",
        ]
        for path in possible_paths:
            if os.path.exists(path):
                chrome_path = path
                break
    
    if not chrome_path or not os.path.exists(chrome_path):
        error_msg = f"[BrowserManager] Chrome not found. Searched locations: "
        if system == "Windows":
            error_msg += "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe, "
            error_msg += "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe, "
            error_msg += "%LOCALAPPDATA%\\Google\\Chrome\\Application\\chrome.exe"
            logger.error(error_msg)
            logger.error("[BrowserManager] Please install Chrome or manually start it with: ")
            logger.error('  chrome.exe --remote-debugging-port=9228 --user-data-dir="C:\\chrome-debug"')
        else:
            error_msg += str(possible_paths)
            logger.error(error_msg)
        return False
    
    logger.info(f"[BrowserManager] Found Chrome at: {chrome_path}")
    
    # Prepare Chrome arguments
    # Each port gets its own user_data_dir to avoid Chrome lockfile conflicts
    # when running multiple instances simultaneously.
    if not user_data_dir:
        _profile_subdir = 'default' if port == 9228 else f'port_{port}'
        try:
            from utils.user_path_helper import ensure_user_data_dir
            user_data_dir = ensure_user_data_dir(subdir=os.path.join('browser_profiles', _profile_subdir))
        except Exception:
            if system == "Windows":
                user_data_dir = os.path.expandvars(f"%TEMP%\\chrome-cdp-{_profile_subdir}")
            else:
                user_data_dir = f"/tmp/chrome-cdp-{_profile_subdir}"

    if not profile_directory:
        profile_directory = "Default"

    args = [
        chrome_path,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={user_data_dir}",
        f"--profile-directory={profile_directory}",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    
    if headless:
        args.append("--headless=new")
    
    try:
        # Start Chrome process
        logger.info(
            f"[BrowserManager] Starting Chrome with CDP on port {port}, "
            f"user_data_dir={user_data_dir}, profile_directory={profile_directory}"
        )
        _chrome_process = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True  # Detach from parent process
        )
        _chrome_port = port
        _chrome_processes[port] = _chrome_process
        
        # Wait for Chrome to start and CDP to be ready
        max_wait = 10  # seconds
        for i in range(max_wait * 2):
            if _is_port_in_use(port):
                logger.info(f"[BrowserManager] Chrome started successfully on port {port}")
                return True
            time.sleep(0.5)
        
        logger.error(f"[BrowserManager] Chrome started but CDP port {port} not ready after {max_wait}s")
        return False
        
    except Exception as e:
        logger.error(f"[BrowserManager] Failed to start Chrome: {e}")
        return False


def _build_browser_session(br_type="existing_chrome", adspower_profile="", port="9228", headless=False) -> BrowserSession:
    """
    Construct a BrowserSession for Native (CDP) mode only.
    
    BrowserSession is used to connect to an existing Chrome instance via CDP.
    Other browser drivers (Selenium, Playwright, Puppeteer) manage their own 
    browsers and don't need BrowserSession.
    
    Args:
        br_type: Browser type ("existing_chrome", "adspower", "new chromium")
        adspower_profile: AdsPower profile ID (for adspower mode)
        port: CDP port number (default: 9228)
        headless: Whether to run in headless mode
        
    Returns:
        BrowserSession instance for CDP connection, or None if browser_use should create its own
    """
    # AdsPower mode: Connect to AdsPower-managed browser
    if br_type == "adspower":
        if not adspower_profile:
            adspower_profile = os.getenv("ADSPOWER_PROFILE_ID", "")
        
        logger.info(f"[BrowserManager] Using AdsPower profile: {adspower_profile}")
        
        if adspower_profile:
            return _build_adspower_browser_session(adspower_profile)
        else:
            logger.warning("[BrowserManager] AdsPower profile not specified, falling back to new chromium")
            return None
    
    # New chromium mode: Let browser_use create its own browser
    if br_type == "new chromium":
        logger.info("[BrowserManager] Using 'new chromium' mode - browser_use will create browser")
        return None
    
    # Native (CDP) mode: Connect to existing Chrome via CDP, auto-start if needed
    cdp_port = int(port) if isinstance(port, str) and port.isdigit() else 9228
    cdp_url = os.getenv("BROWSER_USE_CDP_URL", f"http://127.0.0.1:{cdp_port}")
    
    # Auto-start Chrome if not running
    if not _is_port_in_use(cdp_port):
        logger.info(f"[BrowserManager] Chrome not detected on port {cdp_port}, auto-starting...")
        
        # Ensure persistent user data directory for cookie persistence
        try:
            from utils.user_path_helper import ensure_user_data_dir
            persistent_user_data_dir = ensure_user_data_dir(subdir=os.path.join('browser_profiles', 'default'))
            persistent_profile_dir = "Default"
            logger.info(f"[BrowserManager] Using persistent profile: {persistent_user_data_dir}/{persistent_profile_dir}")
        except Exception as e:
            logger.warning(f"[BrowserManager] Failed to get persistent profile: {e}, using defaults")
            persistent_user_data_dir = None
            persistent_profile_dir = None
        
        if not _start_chrome_with_cdp(
            cdp_port,
            headless,
            user_data_dir=persistent_user_data_dir,
            profile_directory=persistent_profile_dir,
        ):
            logger.warning(f"[BrowserManager] Failed to auto-start Chrome, will attempt to connect anyway")
    
    logger.info(f"[BrowserManager] Using Native (CDP) mode, cdp_url: {cdp_url}")
    profile = BrowserProfile(headless=headless, cdp_url=cdp_url)
    profile.is_local = False
    return BrowserSession(browser_profile=profile, id="ec"+uuid7str())


def _build_adspower_browser_session(profile_id: str) -> BrowserSession:
    """Attach BrowserUse to an AdsPower-managed Chrome profile."""

    api_key = os.getenv("ADSPOWER_API_KEY")
    if not api_key:
        raise RuntimeError("ADSPOWER_API_KEY must be set to use the AdsPower browser variant")

    port_env = os.getenv("ADSPOWER_PORT", "50325")
    try:
        port = int(port_env)
    except ValueError as exc:  # pragma: no cover - defensive parsing
        raise RuntimeError(f"ADSPOWER_PORT must be an integer, got: {port_env!r}") from exc

    print("ads apikey:", api_key, "ads profile_id:", profile_id, "ads port:", port)
    response = startAdspowerProfile(api_key, profile_id, port)
    data = response.get("data", {}) if isinstance(response, dict) else {}
    ws_info = data.get("ws", {}) if isinstance(data, dict) else {}

    # Prefer full devtools websocket endpoint when available
    devtools_ws = ws_info.get("devtools") or ws_info.get("chromedevtools")
    selenium_addr = ws_info.get("selenium") or ws_info.get("webdriver")
    debug_port = data.get("debug_port")

    cdp_url: str | None = None
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
        raise RuntimeError("Failed to determine AdsPower CDP endpoint from startAdspowerProfile response")
    else:
        logger.debug("[BrowserSession] adspower cdp_url:", cdp_url)

    profile = BrowserProfile(headless=False, cdp_url=cdp_url)
    profile.is_local = False
    return BrowserSession(browser_profile=profile, id="ap"+uuid7str())



class UnifiedBrowserManager:
    """Unified browser resource manager"""

    def __init__(self):
        self._lock = Lock()
        self._initialized = False
        self._initialization_error = None

        # Playwright manager
        self._playwright_manager = None

        # Component instances
        self._async_crawler = None
        self._browser_session = None
        self._browser_use_file_system = None

        self._browser_sessions = []

        # Configuration
        self._crawler_config = None
        self._file_system_path = None
        self._browser_agent = None

        
    def initialize(self, crawler_config: Optional[Dict] = None, file_system_path: Optional[str] = None) -> bool:
        """Initialize unified browser manager"""
        with self._lock:
            if self._initialized:
                return True

            if self._initialization_error:
                logger.warning(f"Previous initialization failed: {self._initialization_error}")

            try:
                logger.info("🔧 Starting unified browser manager initialization...")

                if not self._init_playwright_manager():
                    raise RuntimeError("Playwright manager initialization failed")

                # Set environment variables immediately to ensure subsequent components can find browsers
                self._setup_crawler_environment()

                self._setup_crawler_config(crawler_config)
                self._file_system_path = file_system_path
                logger.info("crawler initialized.............")
                self._initialized = True
                self._initialization_error = None
                logger.info("✅ Unified browser manager initialized successfully")

                # Defer crawl4ai initialization; creating it here may bind to the GUI/qasync loop.
                return True

            except Exception as e:
                self._initialization_error = str(e)
                logger.error(f"❌ Unified browser manager initialization failed: {e}")
                return False
    
    def _init_playwright_manager(self) -> bool:
        """Initialize Playwright manager"""
        try:
            self._playwright_manager = get_playwright_manager()

            if not self._playwright_manager.is_initialized():
                logger.info("🔧 Initializing Playwright environment...")
                if not self._playwright_manager.lazy_init():
                    raise RuntimeError("Playwright environment initialization failed")

            logger.info("✅ Playwright manager ready")
            return True

        except Exception as e:
            logger.error(f"Playwright manager initialization failed: {e}")
            return False


    
    def _setup_crawler_config(self, crawler_config: Optional[Dict]):
        """Setup crawler configuration"""
        default_config = {
            'headless': False,
            'verbose': True,
            'viewport_width': 1920,
            'viewport_height': 1080
        }

        if crawler_config:
            default_config.update(crawler_config)

        self._crawler_config = default_config

    def _setup_crawler_environment(self):
        """Setup crawler runtime environment"""
        from pathlib import Path
        from agent.playwright.core.utils import core_utils

        # Ensure Playwright environment variables are set correctly so crawl4ai can find browsers
        if self._playwright_manager and self._playwright_manager.is_initialized():
            browsers_path = self._playwright_manager.get_browsers_path()
            if browsers_path:
                # Use unified environment variable setting function
                core_utils.set_environment_variables(Path(browsers_path))
                logger.debug(f"Set crawler environment variables using core_utils: {browsers_path}")
            else:
                logger.warning("Playwright manager is initialized but browser path is empty")
        else:
            logger.warning("Playwright manager is not initialized or not ready")






    
    def get_async_crawler(self) -> Optional["AsyncWebCrawler"]:
        if not self._initialized:
            logger.warning("Manager not initialized, cannot get AsyncWebCrawler")
            return None

        # Do not create AsyncWebCrawler on GUI/qasync thread to avoid Playwright subprocess errors.
        # Create and use it within a worker thread when needed.
        logger.debug("get_async_crawler called: returning None to avoid creating AsyncWebCrawler on GUI thread")
        return None
    
    def get_browser_session(self) -> Optional['BrowserSession']:
        """Get BrowserSession instance (lazy creation)"""
        if not self._initialized:
            logger.warning("Manager not initialized, cannot get BrowserSession")
            return None

        if self._browser_session is None:
            try:
                from browser_use.browser import BrowserSession as _BrowserSession
                # Note: BrowserSession needs to be created after AsyncWebCrawler is started
                # This is just preparation, actual creation should be done when needed
                logger.debug("BrowserSession will be created when needed")
                return None

            except Exception as e:
                logger.error(f"Failed to prepare BrowserSession: {e}")
                return None

        return self._browser_session



    def create_browser_session(self, br_type="chromium", fpb_profile="") -> Optional['BrowserSession']:
        """Create BrowserSession - fingerprint browser profile"""
        if not self._initialized:
            logger.warning("Manager not initialized, cannot get BrowserSession")
            return None

        if self._browser_session is None:
            try:
                from browser_use.browser import BrowserSession as _BrowserSession
                # Note: BrowserSession needs to be created after AsyncWebCrawler is started
                # This is just preparation, actual creation should be done when needed
                if br_type == "adspower":
                    headless = False
                    logger.debug("BrowserSession adspower will be created when needed")
                    self._browser_session = _build_browser_session(br_type, fpb_profile)
                elif br_type == "existing_chrome":
                    headless = False
                    logger.debug("BrowserSession existing chrome will be created when needed")

                    self._browser_session = _build_browser_session(br_type)
                else:
                    # this is simply bring up a new chromium browser
                    logger.debug("BrowserSession new chromium will be created when needed")
                    self._browser_session = BrowserSession(browser_profile=DEFAULT_BROWSER_PROFILE, id="nc"+uuid7str())
                    print("BrowserSession new chromium created")
                return self._browser_session

            except Exception as e:
                logger.error(f"Failed to prepare BrowserSession: {e}")
                return None

        return self._browser_session


    def _create_bu_agent(self, mainwin=None):
        try:
            if not mainwin:
                raise ValueError("mainwin is required. Must use mainwin.llm from MainWindow. Please configure LLM provider API key in Settings.")
            
            logger.debug("create bu agent....")
            from browser_use import Agent
            from browser_use.browser import BrowserProfile, BrowserSession
            logger.debug("done import browser use....")
            
            # Use mainwin's LLM configuration (no fallback)
            from agent.ec_skills.llm_utils.llm_utils import create_browser_use_llm
            llm = create_browser_use_llm(mainwin=mainwin, skip_playwright_check=True)
            if not llm:
                raise ValueError("Failed to create browser_use LLM from mainwin. Please configure LLM provider API key in Settings.")
            
            BasicConfig = {
                "chrome_path": "",
                "target_user":  "",# Twitter handle without @
                "message":  "",
                "reply_url":  "",
                "headless": True,
                "model": 'gpt-4o',
                "base_url": 'https://www.amazon.com/',
                "product_phrase": "resistance loop band"
            }
            config = BasicConfig
            logger.debug("done config....")
            full_message = f'@{config["target_user"]} {config["message"]}'
            logger.debug("done full message....")
            basic_task = f"""Navigate to Amazon and search a product.
    
                Here are the specific steps:
    
                1. Go to https://www.amazon.com/ See the search text input field at the top of the page"
                2. Look for the text input field at the top of the page that says "What's happening?"
                3. Click the input field and type exactly this product name: '"{config["product_phrase"]}'
                4. Hit <Enter> key
    
                Important:
                - Wait for each element to load before interacting
                - Make sure the search phrase is typed exactly as shown
                """
            logger.debug("done basic task....", basic_task)
            logger.debug("llm set....")
            browser_profile = BrowserProfile(
                headless=config["headless"],
                executable_path=config["chrome_path"],
                minimum_wait_page_load_time=1,  # 3 on prod
                maximum_wait_page_load_time=10,  # 20 on prod
                viewport={'width': 1280, 'height': 1100},
                viewport_expansion=-1,
                highlight_elements=False,
                user_data_dir='~/.config/browseruse/profiles/default',
                # trace_path='./tmp/web_voyager_agent',
            )
            logger.debug("browser profile set....", browser_profile)
            browser_session = BrowserSession(browser_profile=browser_profile)
            logger.debug("browser session set....", browser_session)
            # Construct the full message with tag
            # Create the agent with detailed instructions
            # Auto-detect model vision support and set use_vision accordingly to avoid warnings
            from agent.ec_skills.llm_utils.llm_utils import get_use_vision_from_llm
            agent_kwargs = {
                'task': basic_task,
                'llm': llm,
                'browser_session': browser_session,
                'validate_output': True,
                'enable_memory': False,
                'use_vision': get_use_vision_from_llm(llm, context="UnifiedBrowserManager")
            }
            agent = Agent(**agent_kwargs)
            logger.debug("browser agent set....", browser_session)
            return agent

        except Exception as e:
            errMsg = get_traceback(e, "ErrorCreateBUAgent")
            logger.debug(errMsg)
            return None



    def get_browser_user(self) -> Optional['Agent']:
        """Get BrowserSession instance (lazy creation)"""
        if not self._initialized:
            logger.warning("Manager not initialized, cannot get BrowserSession")
            return None

        # Do not create Browser Use Agent on GUI/qasync thread to avoid Playwright subprocess errors.
        # Agent will be created and run within run_basic_agent_task() on a worker thread.
        logger.debug("get_browser_user called: returning None to avoid creating Agent on GUI thread")
        return None

    def run_basic_agent_task(self, product_phrase: Optional[str] = None, mainwin=None):
        """Build and run a simple Browser Use agent inside a worker thread with its own Selector loop.

        This avoids running Playwright on the GUI/qasync loop (which lacks subprocess support on Windows).
        
        Args:
            product_phrase: Optional product phrase to search for
            mainwin: MainWindow instance (required, no fallback)
        """
        if not mainwin:
            raise ValueError("mainwin is required. Must use mainwin.llm from MainWindow. Please configure LLM provider API key in Settings.")
        
        async def _do():
            try:
                loop = asyncio.get_running_loop()
                logger.info(f"[UnifiedBrowserManager._do] loop={type(loop).__name__}")
            except Exception:
                pass
            from browser_use import Agent
            from browser_use.browser import BrowserProfile, BrowserSession

            cfg_phrase = product_phrase or "resistance loop band"
            task_text = f"""Navigate to Amazon and search a product.
                1. Go to https://www.amazon.com/
                2. Focus the top search input
                3. Type exactly: '{cfg_phrase}'
                4. Press Enter and wait for results
            """

            # Use mainwin's LLM configuration (no fallback)
            from agent.ec_skills.llm_utils.llm_utils import create_browser_use_llm
            llm = create_browser_use_llm(mainwin=mainwin, skip_playwright_check=True)
            if not llm:
                raise ValueError("Failed to create browser_use LLM from mainwin. Please configure LLM provider API key in Settings.")
            browser_profile = BrowserProfile(
                headless=False,
                executable_path='',
                minimum_wait_page_load_time=1,
                maximum_wait_page_load_time=12,
                viewport={'width': 1280, 'height': 1100},
                viewport_expansion=-1,
                highlight_elements=False,
                user_data_dir='~/.config/browseruse/profiles/default',
                keep_alive=True,
            )
            browser_session = BrowserSession(browser_profile=browser_profile)

            # Auto-detect model vision support and set use_vision accordingly to avoid warnings
            from agent.ec_skills.llm_utils.llm_utils import get_use_vision_from_llm
            agent_kwargs = {
                'task': task_text,
                'llm': llm,
                'browser_session': browser_session,
                'validate_output': True,
                'enable_memory': False,
                'use_vision': get_use_vision_from_llm(llm, context="UnifiedBrowserManager._do")
            }
            agent = Agent(**agent_kwargs)

            history = await agent.run()
            return history

        try:
            return run_async_in_worker_thread(lambda: _do())
        except Exception as e:
            logger.error(f"Failed to run Browser Use agent task: {e}")
            logger.debug(get_traceback(e, "ErrorRunBasicAgentTask"))
            return None


    
    def get_browser_use_file_system(self) -> Optional['FileSystem']:
        if not self._initialized:
            logger.warning("Manager not initialized, cannot get BrowserUse FileSystem")
            return None

        if self._browser_use_file_system is None:
            from browser_use.filesystem.file_system import FileSystem
            try:
                if self._file_system_path:
                    self._browser_use_file_system = FileSystem(self._file_system_path)
                    logger.debug(f"✅ BrowserUse FileSystem created successfully, path: {self._file_system_path}")
                else:
                    self._browser_use_file_system = FileSystem()
                    logger.debug("✅ BrowserUse FileSystem created successfully (default path)")
            except Exception as e:
                logger.error(f"Failed to create BrowserUse FileSystem: {e}")
                return None

        return self._browser_use_file_system

    def run_browser_use_coro(self, coro_factory):
        """
        Run an arbitrary Browser Use async coroutine in the dedicated worker thread.

        Args:
            coro_factory: A zero-arg callable that returns an async coroutine.
                The coroutine MUST import and create any Browser Use / Playwright objects
                inside itself so they bind to the worker thread's Proactor event loop.

        Returns:
            The coroutine's return value (synchronously), or None on failure.

        Notes:
            - This ensures we do NOT touch the GUI/qasync loop and avoid subprocess errors on Windows.
            - Internally uses run_async_in_worker_thread with WindowsProactorEventLoopPolicy.
        """
        try:
            # Ensure manager is initialized for environment setup
            if not self._initialized:
                logger.warning("Manager not initialized; initializing with defaults before running coroutine")
                if not self.initialize():
                    logger.error("Failed to initialize UnifiedBrowserManager")
                    return None

            return run_async_in_worker_thread(lambda: coro_factory())
        except Exception as e:
            logger.error(f"Failed to run Browser Use coroutine in worker thread: {e}")
            logger.debug(get_traceback(e, "ErrorRunBrowserUseCoro"))
            return None
    
    def cleanup(self):
        """Clean up all resources"""
        with self._lock:
            try:
                # Clean up component instances
                self._async_crawler = None
                self._browser_session = None
                self._browser_use_file_system = None

                self._initialized = False
                self._initialization_error = None
                logger.debug("Unified browser manager resources cleaned up")
            except Exception as e:
                logger.warning(f"Error during resource cleanup: {e}")

    def is_ready(self) -> bool:
        """Check if manager is ready to provide services"""
        return self._initialized and self._initialization_error is None

    def get_status(self) -> Dict[str, Any]:
        """Get manager status"""
        return {
            'initialized': self._initialized,
            'ready': self.is_ready(),
            'initialization_error': self._initialization_error,
            'async_crawler_ready': self._async_crawler is not None,
            'browser_session_ready': self._browser_session is not None,
            'browser_use_file_system_ready': self._browser_use_file_system is not None,
            'playwright_manager_status': self._playwright_manager.get_status() if self._playwright_manager else None
        }

    def switch_profile(self, new_profile):
        # close old
        try:
            if self._browser_session and hasattr(self._browser_session, "close"):
                self._browser_session.close()
            elif self._browser_session and hasattr(self._browser_session, "shutdown"):
                self._browser_session.shutdown()
        except Exception:
            pass

        # create new
        self._browser_session = BrowserSession(browser_profile=new_profile)

        # rebuild agent if needed (safer than mutating in place)
        if self._browser_agent is not None:
            # self._browser_agent = Agent(task=..., llm=..., browser_session=self._browser_session)
            pass

        return self._browser_session



# Global manager instance
_unified_manager_instance: Optional[UnifiedBrowserManager] = None
_unified_manager_lock = Lock()


def get_unified_browser_manager() -> UnifiedBrowserManager:
    """
    Get global unified browser manager instance (singleton pattern)

    Returns:
        UnifiedBrowserManager: Manager instance
    """
    global _unified_manager_instance

    if _unified_manager_instance is None:
        with _unified_manager_lock:
            if _unified_manager_instance is None:
                _unified_manager_instance = UnifiedBrowserManager()

    return _unified_manager_instance
