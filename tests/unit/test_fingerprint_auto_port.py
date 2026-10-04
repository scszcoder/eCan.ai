"""A store's profile browser on "auto" gets a free port of its own, never the 9228 slot.

Customer run 99r: two front desks resolved cdp_port=auto, BrowserManager turned
auto into the plain-Chrome slot pool's first port (9228) for both, and their
browsers collided on it. Store processes (two stores of one platform) cannot
share an in-process launch lock, so the port itself must not be shared.
"""

from gui.manager.browser_manager import BrowserManager, BrowserStatus, BrowserType


class _Made:
    def __init__(self, port):
        self.id, self.cdp_port, self.status = f"b{port}", port, BrowserStatus.IDLE
        self.browser_session, self.slot_id, self.profile = None, None, None
    def mark_in_use(self, *a, **k):
        self.status = BrowserStatus.IN_USE


def _manager(monkeypatch):
    bm = BrowserManager()
    asked = []

    def _create(**kw):
        asked.append((kw["browser_type"], kw["cdp_port"], kw.get("profile")))
        return _Made(kw["cdp_port"])

    monkeypatch.setattr(bm, "create_browser", _create)
    monkeypatch.setattr(bm, "register_browser", lambda b: b.id, raising=False)
    return bm, asked


def test_fingerprint_auto_port_is_left_to_the_profile_launcher(monkeypatch):
    bm, asked = _manager(monkeypatch)
    for store, profile_id in (("a", "douyin-store-a"), ("b", "douyin-store-b")):
        bm.acquire_browser(agent_id=f"fd_{store}", task="t", browser_type=BrowserType.FINGERPRINT,
                           cdp_port=0, adspower_profile_id=profile_id)
    assert [port for _t, port, _p in asked] == [0, 0], asked
    assert all(p is None for _t, _port, p in asked), "no plain-Chrome slot profile (C:\\chrome_data) on a store"


def test_plain_chrome_auto_still_uses_the_slot_pool(monkeypatch):
    bm, asked = _manager(monkeypatch)
    bm.acquire_browser(agent_id="x", task="t", browser_type=BrowserType.CHROME, cdp_port=0)
    assert asked[0][1] == 9228
