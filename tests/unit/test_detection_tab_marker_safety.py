"""A store URL saved with eCan's detection-tab marker (``#ecan_det``) made the
agent's own main tab look like a leftover detection tab; the stale sweep closed
it, Chrome exited with its last tab, and the store stayed dead for 8 h
(2026-10-18, two 抖店 stores). Covers: the marker is stripped before navigating
and when saving, and the sweep never closes the new tab, the agent's focused
tab, or another agent's live detection tab from this session."""
import asyncio
import sys
import types
from types import SimpleNamespace

from utils.detection_tab import strip_detection_marker

STORE = "https://im.jinritemai.com/pc_seller_v2/main/workspace"


def test_strip_marker():
    assert strip_detection_marker(STORE + "#ecan_det") == STORE
    assert strip_detection_marker(STORE) == STORE
    assert strip_detection_marker(STORE + "#other") == STORE + "#other"
    assert strip_detection_marker(None) is None


def test_runner_never_navigates_a_store_tab_to_the_marker():
    from agent.ec_skills.browser_node.runner import extract_store_url
    assert extract_store_url({"prompt_refs": {"store_url": STORE + "#ecan_det"}}) == STORE
    assert extract_store_url({"prompt_refs": {"store_urls": [STORE + "#ecan_det"]}}) == STORE


def test_store_service_saves_without_the_marker():
    import json
    from sqlalchemy import create_engine
    from agent.db.core.base import Base
    from agent.db.services.db_store_service import DBStoreService
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    svc = DBStoreService(engine=engine)
    svc.upsert_store({"store_id": "douyin-B", "name": "B", "platform": "douyin",
                      "store_urls": [STORE + "#ecan_det"]})
    rows = svc.list_stores() if hasattr(svc, "list_stores") else None
    from agent.db.models.store_model import Store
    with svc.session_scope() as s:
        saved = json.loads(s.query(Store).filter(Store.store_id == "douyin-B").first().store_urls)
    assert saved == [STORE]


class _FakeCDP:
    """Browser with pages; closing the last page 'kills' the browser."""
    pages = {}
    closed = []
    created = []

    def __init__(self, url=None):
        pass

    async def start(self):
        pass

    async def stop(self):
        pass

    async def send_raw(self, method, params):
        if method == "Target.createTarget":
            tid = f"NEW{len(_FakeCDP.created)}"
            _FakeCDP.created.append(tid)
            _FakeCDP.pages[tid] = params["url"]
            return {"targetId": tid}
        if method == "Target.getTargets":
            return {"targetInfos": [{"type": "page", "targetId": t, "url": u} for t, u in _FakeCDP.pages.items()]}
        if method == "Target.closeTarget":
            _FakeCDP.closed.append(params["targetId"])
            _FakeCDP.pages.pop(params["targetId"], None)
            return {}


def _open(monkeypatch, pages, focus=""):
    from agent.ec_skills.browser_use_extension import event_monitor as em
    _FakeCDP.pages = dict(pages)
    _FakeCDP.closed = []
    monkeypatch.setitem(sys.modules, "cdp_use", types.SimpleNamespace(CDPClient=_FakeCDP))
    session = SimpleNamespace(cdp_url="ws://x", agent_focus_target_id=focus)
    return asyncio.run(em._open_detection_tab(session, STORE)), em


def test_marked_main_tab_is_not_closed_and_browser_keeps_a_tab(monkeypatch):
    # The customer's case: the only tab is the agent's main tab at STORE#ecan_det.
    tid, _ = _open(monkeypatch, {"MAIN": STORE + "#ecan_det"}, focus="MAIN")
    assert tid and "MAIN" not in _FakeCDP.closed
    assert _FakeCDP.pages            # never left with zero tabs


def test_leftover_from_previous_session_is_still_closed(monkeypatch):
    tid, _ = _open(monkeypatch, {"MAIN": STORE, "OLD": STORE + "#ecan_det"}, focus="MAIN")
    assert _FakeCDP.closed == ["OLD"] and tid in _FakeCDP.pages and "MAIN" in _FakeCDP.pages


def test_other_agents_live_detection_tab_is_not_closed(monkeypatch):
    # Agent A opens its detection tab, then agent B (same browser) opens its own.
    tid_a, em = _open(monkeypatch, {"MAIN_A": STORE}, focus="MAIN_A")
    pages_after_a = dict(_FakeCDP.pages)
    _FakeCDP.closed = []
    from agent.ec_skills.browser_use_extension import event_monitor as em2
    session_b = SimpleNamespace(cdp_url="ws://x", agent_focus_target_id="MAIN_B")
    _FakeCDP.pages = {**pages_after_a, "MAIN_B": STORE}
    tid_b = asyncio.run(em2._open_detection_tab(session_b, STORE))
    assert tid_a not in _FakeCDP.closed and tid_a in _FakeCDP.pages and tid_b in _FakeCDP.pages
