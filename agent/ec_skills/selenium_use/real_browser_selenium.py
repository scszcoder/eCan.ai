from __future__ import annotations

import asyncio
import os
from functools import wraps

from dotenv import load_dotenv

from browser_use import Agent, BrowserSession
from browser_use.browser.profile import BrowserProfile
from browser_use.llm.openai.chat import ChatOpenAI

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


def _build_browser_session() -> BrowserSession:
    """Construct a BrowserSession.

    Priority:
    1. If ADSPOWER_PROFILE_ID is set, attach to the AdsPower fingerprint browser.
    2. Otherwise, attach to a generic Chrome instance using BROWSER_USE_CDP_URL
       (defaults to http://127.0.0.1:9228).
    """
    from browser_use.browser.session import DEFAULT_BROWSER_PROFILE

    adspower_profile = os.getenv("ADSPOWER_PROFILE_ID", "")
    print("ads_profile:", adspower_profile)
    # if adspower_profile:
    #     return _build_adspower_browser_session(adspower_profile)

    cdp_url = os.getenv("BROWSER_USE_CDP_URL", "http://127.0.0.1:9228")
    print("cdp_url:", cdp_url)
    profile = BrowserProfile(headless=False, cdp_url=cdp_url)
    profile.is_local = False
    profile = DEFAULT_BROWSER_PROFILE
    return BrowserSession(browser_profile=profile)


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

    profile = BrowserProfile(headless=False, cdp_url=cdp_url)
    profile.is_local = False
    return BrowserSession(browser_profile=profile)


async def main() -> None:
    session = _build_browser_session()

    agent = Agent(
        llm=LoggingChatOpenAI(model="gpt-4.1-mini"),
        task="go to amazon.com and search for pens to draw on whiteboards",
        browser_session=session,
    )

    # await asyncio.sleep(10)
    await agent.run()


if __name__ == "__main__":
    asyncio.run(main())
