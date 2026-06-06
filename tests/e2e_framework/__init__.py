"""E2E Test Framework - Browser Launcher and CDP Connector.

This module provides:
1. Browser launcher with configurable options (Chrome/Firefox with remote debugging)
2. CDP connection manager for direct browser automation
3. Integration with Playwright for standard web automation
4. Test environment setup utilities

Usage:
    # Option 1: Auto-launch browser
    from tests.e2e_framework import BrowserLauncher, CDPBrowser

    browser = BrowserLauncher.launch(headless=False, cdp_port=9222)
    session = await browser.connect()

    # Option 2: Connect to existing browser via CDP
    from tests.e2e_framework import CDPConnector
    cdp = CDPConnector("ws://localhost:9222/devtools/browser/...")
    page = await cdp.new_page()

    # Option 3: Use Playwright directly
    from tests.e2e_framework import get_playwright
    pw = await get_playwright()
    browser = await pw.chromium.launch()
"""

import asyncio
import json
import subprocess
import sys
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse

# Add project root to path
_ROOT = Path(__file__).parent.parent.parent.resolve()
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


class BrowserType(Enum):
    CHROME = "chrome"
    FIREFOX = "firefox"
    EDGE = "edge"


@dataclass
class BrowserConfig:
    """Configuration for browser launch."""
    browser_type: BrowserType = BrowserType.CHROME
    headless: bool = False
    cdp_port: int = 9222
    user_data_dir: Optional[str] = None
    window_size: tuple = (1920, 1080)
    extra_args: List[str] = field(default_factory=list)
    stealth: bool = True

    def to_chrome_args(self) -> List[str]:
        """Generate Chrome/Edge launch arguments."""
        args = [
            f"--remote-debugging-port={self.cdp_port}",
            f"--window-size={self.window_size[0]},{self.window_size[1]}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-extensions",
            "--disable-popup-blocking",
            "--disable-notifications",
            "--disable-infobars",
            "--disable-session-crashed-bubble",
            "--disable-dev-shm-usage",
        ]

        if self.headless:
            args.append("--headless=new")
            args.append("--disable-gpu")

        if self.user_data_dir:
            args.append(f"--user-data-dir={self.user_data_dir}")

        if self.stealth:
            args.extend([
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
            ])

        args.extend(self.extra_args)
        return args

    def to_firefox_args(self) -> List[str]:
        """Generate Firefox launch arguments."""
        args = [
            "--width=" + str(self.window_size[0]),
            "--height=" + str(self.window_size[1]),
        ]

        if self.headless:
            args.append("--headless")

        args.extend(self.extra_args)
        return args


class BrowserLauncher:
    """Launch and manage browser instances with CDP support."""

    _instances: Dict[str, subprocess.Popen] = {}

    @classmethod
    def launch(
        cls,
        browser_type: BrowserType = BrowserType.CHROME,
        headless: bool = False,
        cdp_port: int = 9222,
        user_data_dir: Optional[str] = None,
        stealth: bool = True,
        wait_ready: bool = True,
        timeout: int = 30,
    ) -> subprocess.Popen:
        """Launch a browser instance with CDP debugging enabled.

        Args:
            browser_type: Which browser to launch
            headless: Run in headless mode
            cdp_port: CDP debugging port
            user_data_dir: Custom user data directory
            stealth: Apply anti-detection measures
            wait_ready: Wait for browser to be ready
            timeout: Timeout for browser launch

        Returns:
            subprocess.Popen handle to the browser process
        """
        config = BrowserConfig(
            browser_type=browser_type,
            headless=headless,
            cdp_port=cdp_port,
            user_data_dir=user_data_dir,
            stealth=stealth,
        )

        if browser_type == BrowserType.CHROME:
            return cls._launch_chrome(config, wait_ready, timeout)
        elif browser_type == BrowserType.EDGE:
            return cls._launch_edge(config, wait_ready, timeout)
        elif browser_type == BrowserType.FIREFOX:
            return cls._launch_firefox(config, wait_ready, timeout)
        else:
            raise ValueError(f"Unsupported browser type: {browser_type}")

    @classmethod
    def _launch_chrome(cls, config: BrowserConfig, wait_ready: bool, timeout: int) -> subprocess.Popen:
        """Launch Chrome browser."""
        chrome_paths = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/snap/bin/chromium",
            "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
        ]

        chrome_cmd = None
        for path in chrome_paths:
            if Path(path).exists():
                chrome_cmd = path
                break

        if not chrome_cmd:
            result = subprocess.run(
                ["which", "google-chrome"] if sys.platform != "win32" else ["where", "chrome"],
                capture_output=True, text=True,
            )
            if result.returncode == 0:
                chrome_cmd = result.stdout.strip()

        if not chrome_cmd:
            raise RuntimeError("Chrome not found. Please install Chrome or specify the path.")

        args = config.to_chrome_args()

        if not config.user_data_dir:
            import tempfile
            temp_dir = tempfile.mkdtemp(prefix="e2e_chrome_")
            args.append(f"--user-data-dir={temp_dir}")

        cmd = [chrome_cmd] + args
        print(f"[BrowserLauncher] Launching Chrome: {' '.join(cmd)}")

        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        instance_id = f"chrome_{config.cdp_port}"
        cls._instances[instance_id] = proc

        if wait_ready:
            cls._wait_for_ready(config.cdp_port, timeout)

        return proc

    @classmethod
    def _launch_edge(cls, config: BrowserConfig, wait_ready: bool, timeout: int) -> subprocess.Popen:
        """Launch Edge browser."""
        edge_paths = [
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "/usr/bin/microsoft-edge",
            "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
        ]

        edge_cmd = None
        for path in edge_paths:
            if Path(path).exists():
                edge_cmd = path
                break

        if not edge_cmd:
            raise RuntimeError("Edge not found")

        args = config.to_chrome_args()
        cmd = [edge_cmd] + args
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        instance_id = f"edge_{config.cdp_port}"
        cls._instances[instance_id] = proc

        if wait_ready:
            cls._wait_for_ready(config.cdp_port, timeout)

        return proc

    @classmethod
    def _launch_firefox(cls, config: BrowserConfig, wait_ready: bool, timeout: int) -> subprocess.Popen:
        """Launch Firefox browser with remote debugging."""
        firefox_paths = [
            "/Applications/Firefox.app/Contents/MacOS/firefox",
            "/usr/bin/firefox",
        ]

        firefox_cmd = None
        for path in firefox_paths:
            if Path(path).exists():
                firefox_cmd = path
                break

        if not firefox_cmd:
            raise RuntimeError("Firefox not found")

        args = [
            "--start-debugging-server",
            f"localhost:{config.cdp_port}",
        ] + config.to_firefox_args()

        cmd = [firefox_cmd] + args
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        instance_id = f"firefox_{config.cdp_port}"
        cls._instances[instance_id] = proc

        if wait_ready:
            time.sleep(3)

        return proc

    @classmethod
    def _wait_for_ready(cls, port: int, timeout: int) -> None:
        """Wait for browser CDP to be ready."""
        import urllib.request

        endpoint = f"http://localhost:{port}/json/version"
        start = time.time()

        while time.time() - start < timeout:
            try:
                with urllib.request.urlopen(endpoint, timeout=2) as resp:
                    if resp.status == 200:
                        print(f"[BrowserLauncher] Browser ready on port {port}")
                        return
            except Exception:
                pass
            time.sleep(0.5)

        raise TimeoutError(f"Browser failed to start within {timeout}s")

    @classmethod
    def get_cdp_ws_url(cls, port: int, target_id: Optional[str] = None) -> str:
        """Get WebSocket URL for CDP connection."""
        import urllib.request

        try:
            with urllib.request.urlopen(f"http://localhost:{port}/json", timeout=5) as resp:
                targets = json.loads(resp.read().decode())

            if not targets:
                raise RuntimeError("No browser targets found")

            if target_id:
                for t in targets:
                    if t.get("id") == target_id:
                        return t["webSocketDebuggerUrl"]
                raise ValueError(f"Target {target_id} not found")

            return targets[0]["webSocketDebuggerUrl"]
        except Exception as e:
            raise RuntimeError(f"Failed to get CDP URL: {e}")

    @classmethod
    def get_targets(cls, port: int) -> List[Dict[str, Any]]:
        """Get all browser targets (tabs, pages)."""
        import urllib.request

        try:
            with urllib.request.urlopen(f"http://localhost:{port}/json", timeout=5) as resp:
                return json.loads(resp.read().decode())
        except Exception as e:
            raise RuntimeError(f"Failed to get targets: {e}")

    @classmethod
    def close(cls, port: int) -> None:
        """Close browser instance."""
        for key, proc in list(cls._instances.items()):
            if str(port) in key:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                del cls._instances[key]
                print(f"[BrowserLauncher] Closed browser on port {port}")

    @classmethod
    def close_all(cls) -> None:
        """Close all browser instances."""
        for key, proc in list(cls._instances.items()):
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        cls._instances.clear()
        print("[BrowserLauncher] Closed all browsers")


class CDPConnector:
    """Connect to browser via Chrome DevTools Protocol."""

    def __init__(self, ws_url: str):
        self.ws_url = ws_url
        self.ws: Optional[Any] = None
        self._msg_id = 0
        self._pending: Dict[int, asyncio.Future] = {}

    async def connect(self) -> None:
        """Establish WebSocket connection."""
        import websockets

        self.ws = await websockets.connect(self.ws_url)
        asyncio.create_task(self._receive_loop())

    async def _receive_loop(self) -> None:
        """Receive messages from CDP."""
        if not self.ws:
            return

        try:
            async for msg in self.ws:
                data = json.loads(msg)
                msg_id = data.get("id")
                if msg_id and msg_id in self._pending:
                    future = self._pending.pop(msg_id)
                    if "error" in data:
                        future.set_exception(Exception(data["error"].get("message", "Unknown error")))
                    else:
                        future.set_result(data.get("result"))
        except Exception as e:
            print(f"[CDPConnector] Receive error: {e}")

    async def send(self, method: str, params: Optional[Dict] = None) -> Any:
        """Send CDP command and wait for response."""
        if not self.ws:
            raise RuntimeError("Not connected")

        self._msg_id += 1
        msg_id = self._msg_id
        future = asyncio.get_event_loop().create_future()
        self._pending[msg_id] = future

        msg = {"id": msg_id, "method": method}
        if params:
            msg["params"] = params

        await self.ws.send(json.dumps(msg))
        return await future

    async def close(self) -> None:
        """Close connection."""
        if self.ws:
            await self.ws.close()
            self.ws = None


class CDPPage:
    """High-level CDP page operations."""

    def __init__(self, cdp: CDPConnector):
        self.cdp = cdp
        self.page_id: Optional[str] = None

    async def enable(self) -> None:
        """Enable Page domain."""
        await self.cdp.send("Page.enable")

    async def navigate(self, url: str) -> Dict[str, Any]:
        """Navigate to URL."""
        result = await self.cdp.send("Page.navigate", {"url": url})
        return result or {}

    async def wait_for_load(self, timeout: int = 30000) -> None:
        """Wait for page to load."""
        await self.cdp.send("Page.setDownloadBehavior", {"behavior": "allow"})
        start = time.time()
        while time.time() - start < timeout / 1000:
            result = await self.cdp.send("DOM.getDocument", {"depth": 0})
            if result and result.get("root"):
                return
            await asyncio.sleep(0.5)
        raise TimeoutError("Page load timeout")

    async def evaluate(self, expression: str) -> Any:
        """Execute JavaScript in page context."""
        result = await self.cdp.send("Runtime.evaluate", {
            "expression": expression,
            "returnByValue": True,
        })
        if result and "result" in result:
            return result["result"].get("value")
        return None

    async def get_element_text(self, selector: str) -> Optional[str]:
        """Get text content of element."""
        script = f"""
            (() => {{
                const el = document.querySelector('{selector}');
                return el ? el.textContent : null;
            }})()
        """
        return await self.evaluate(script)

    async def click(self, selector: str) -> None:
        """Click element."""
        script = f"""
            (() => {{
                const el = document.querySelector('{selector}');
                if (el) el.click();
            }})()
        """
        await self.evaluate(script)

    async def fill_input(self, selector: str, value: str) -> None:
        """Fill input field."""
        script = f"""
            (() => {{
                const el = document.querySelector('{selector}');
                if (el) {{
                    el.value = '{value}';
                    el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                }}
            }})()
        """
        await self.evaluate(script)

    async def screenshot(self) -> bytes:
        """Take screenshot."""
        result = await self.cdp.send("Page.captureScreenshot", {"format": "png"})
        if result and "data" in result:
            import base64
            return base64.b64decode(result["data"])
        return b""


async def get_playwright():
    """Get Playwright instance (lazy import)."""
    try:
        from playwright.async_api import async_playwright
        return await async_playwright().start()
    except ImportError:
        raise RuntimeError(
            "Playwright not installed. Run: pip install playwright && playwright install chromium"
        )


class E2ETestContext:
    """Context manager for E2E test execution."""

    def __init__(
        self,
        base_url: str = "http://localhost:3000",
        cdp_port: int = 9222,
        headless: bool = False,
        browser_type: BrowserType = BrowserType.CHROME,
    ):
        self.base_url = base_url
        self.cdp_port = cdp_port
        self.headless = headless
        self.browser_type = browser_type
        self.browser_proc: Optional[subprocess.Popen] = None
        self.cdp: Optional[CDPConnector] = None
        self.page: Optional[CDPPage] = None
        self.playwright = None
        self.pw_browser = None
        self.pw_page = None

    async def __aenter__(self) -> "E2ETestContext":
        """Setup test environment."""
        self.browser_proc = BrowserLauncher.launch(
            browser_type=self.browser_type,
            headless=self.headless,
            cdp_port=self.cdp_port,
        )

        ws_url = BrowserLauncher.get_cdp_ws_url(self.cdp_port)

        self.cdp = CDPConnector(ws_url)
        await self.cdp.connect()

        self.page = CDPPage(self.cdp)
        await self.page.enable()

        try:
            self.playwright = await get_playwright()
            self.pw_browser = await self.playwright.chromium.connect_over_cdp(ws_url)
            self.pw_page = await self.pw_browser.new_page()
        except Exception as e:
            print(f"[E2ETestContext] Playwright connection failed: {e}")

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Cleanup test environment."""
        if self.pw_page:
            await self.pw_page.close()
        if self.pw_browser:
            await self.pw_browser.close()
        if self.playwright:
            await self.playwright.stop()
        if self.cdp:
            await self.cdp.close()
        if self.browser_proc:
            BrowserLauncher.close(self.cdp_port)


async def create_test_context(
    base_url: str = "http://localhost:3000",
    cdp_port: int = 9222,
    headless: bool = True,
) -> E2ETestContext:
    """Create E2E test context."""
    ctx = E2ETestContext(
        base_url=base_url,
        cdp_port=cdp_port,
        headless=headless,
    )
    await ctx.__aenter__()
    return ctx


if __name__ == "__main__":
    print("Launching browser with CDP...")
    proc = BrowserLauncher.launch(cdp_port=9222, headless=False)
    print(f"Browser PID: {proc.pid}")

    targets = BrowserLauncher.get_targets(9222)
    print(f"Available targets: {len(targets)}")
    for t in targets:
        print(f"  - {t.get('title', 'Untitled')}: {t.get('url', '')}")

    ws_url = BrowserLauncher.get_cdp_ws_url(9222)
    print(f"CDP WebSocket URL: {ws_url}")

    input("Press Enter to close browser...")
    BrowserLauncher.close(9222)
