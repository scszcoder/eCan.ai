"""A reused browser session gets its browser address back after browser-use's
reset() cleared it (2026-10-24 KEN: every second chore run in a session --
the 2:30 promotions after the 2:00 export -- attached to nothing)."""
import asyncio

from browser_use.browser.profile import BrowserProfile
from browser_use.browser.session import BrowserSession

from agent.ec_skills.browser_node.build_helpers import restore_session_cdp_url


def test_a_reset_session_is_pointed_back_at_its_browser():
    s = BrowserSession(browser_profile=BrowserProfile(cdp_url="http://127.0.0.1:58212", is_local=True))
    asyncio.run(s.reset())
    assert s.cdp_url is None                          # what browser-use does
    assert restore_session_cdp_url(s, 58212) and s.cdp_url == "http://127.0.0.1:58212"


def test_a_session_that_still_knows_its_browser_is_left_alone():
    s = BrowserSession(browser_profile=BrowserProfile(cdp_url="http://127.0.0.1:1111", is_local=True))
    assert not restore_session_cdp_url(s, 58212) and s.cdp_url == "http://127.0.0.1:1111"
    assert not restore_session_cdp_url(s, 0)
