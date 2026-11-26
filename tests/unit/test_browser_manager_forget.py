"""A browser record whose session failed to start is dropped, not handed to the next run (2026-11-24)."""
from gui.manager.browser_manager import AutoBrowser, BrowserManager, BrowserType


def test_a_forgotten_browser_is_gone_and_its_browser_is_left_alone():
    closed = []

    class Session:
        async def close(self):
            closed.append(True)

    bm = BrowserManager()
    b = AutoBrowser(browser_type=BrowserType.FINGERPRINT, browser_session=Session())
    bm._browsers[b.id] = b
    assert bm.forget_browser(b.id)
    assert b.id not in bm._browsers and not closed
    assert not bm.forget_browser(b.id)
