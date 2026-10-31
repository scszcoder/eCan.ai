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


class _Browser:
    id = "ab_1"

    def __init__(self, session):
        self.browser_session = session


def test_a_stopped_session_is_replaced_by_a_new_one_on_the_same_browser():
    # 2026-10-24 KEN: the second chore of an app session got back the session the
    # first one had stopped; its start() returned at once with zero tabs.
    from agent.ec_skills.browser_node.build_helpers import renew_stopped_session
    old = BrowserSession(browser_profile=BrowserProfile(is_local=True, downloads_path="C:/dl"), id="ec_old")
    b = _Browser(old)
    assert renew_stopped_session(b, 54091, stale_session=old)
    new = b.browser_session
    assert new is not old and new.id.startswith("ec_") and new.id != "ec_old"
    assert new.cdp_url == "http://127.0.0.1:54091" and str(new.browser_profile.downloads_path).endswith("dl")
    assert old.cdp_url is None                      # the old profile object is not shared


def test_a_session_whose_event_queue_shut_down_is_renewed_too():
    from types import SimpleNamespace
    from agent.ec_skills.browser_node.build_helpers import renew_stopped_session
    old = BrowserSession(browser_profile=BrowserProfile(cdp_url="http://127.0.0.1:1", is_local=True))
    object.__setattr__(old, "event_bus", SimpleNamespace(event_queue=SimpleNamespace(_is_shutdown=True)))
    b = _Browser(old)
    assert renew_stopped_session(b, 1) and b.browser_session.cdp_url == "http://127.0.0.1:1"


def test_a_live_session_is_kept():
    from agent.ec_skills.browser_node.build_helpers import renew_stopped_session
    s = BrowserSession(browser_profile=BrowserProfile(cdp_url="http://127.0.0.1:1", is_local=True))
    b = _Browser(s)
    assert not renew_stopped_session(b, 1, stale_session=None) and b.browser_session is s


def test_a_session_that_browser_use_killed_is_renewed():
    # KEN 2026-10-29 run 31: kill()/stop() leave a fresh EventBus with no handlers,
    # so start() "succeeded" in 0 ms attached to nothing.
    from agent.ec_skills.browser_node.build_helpers import renew_stopped_session
    from bubus import EventBus
    old = BrowserSession(browser_profile=BrowserProfile(cdp_url="http://127.0.0.1:1", is_local=True))
    old.event_bus = EventBus()                     # what kill()/stop() end with
    b = _Browser(old)
    assert renew_stopped_session(b, 1) and b.browser_session is not old
    assert b.browser_session.event_bus.handlers.get("BrowserStartEvent")
