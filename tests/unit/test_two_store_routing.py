"""Two 抖店 stores on one machine (customer run 2026-10-19, yas).

Each store has its own fingerprint Chrome, but BrowserManager gave both
attached sessions the same placeholder user_data_dir, so shop_key_of saw one
store: both front desks wrote one dispatch slot, every WS message ran as the
last front desk (store 三号), and replies went to the wrong store. send_chat's
auto-distribute then also rotated Q&A replies between the two front desks."""
import importlib
from types import SimpleNamespace

import pytest

DEFAULT_DIR = r"C:\Users\Admin\AppData\Local\eCan.cn\x_local\browser_profiles\default"


def _session(port):
    return SimpleNamespace(cdp_url=f"http://127.0.0.1:{port}",
                           browser_profile=SimpleNamespace(user_data_dir=DEFAULT_DIR, cdp_url=None))


def _state(pid, udd=""):
    return {"attributes": {"params": {"browser_profile_id": pid, "user_data_dir": udd}}}


@pytest.fixture
def shop_mods(monkeypatch):
    ws = importlib.import_module("agent.ec_skills.browser_use_extension.hooks.external.feige_chat.ws_session")
    fd = importlib.import_module("agent.ec_skills.browser_use_extension.hooks.external.feige_chat.front_desk")
    sc = importlib.import_module("agent.ec_skills.browser_use_extension.hooks.external.feige_chat.shop_scope")
    bh = importlib.import_module("agent.ec_skills.browser_node.build_helpers")
    monkeypatch.setattr(ws, "_first_shop", [""])
    monkeypatch.setattr(ws, "_shops", {})
    monkeypatch.setattr(fd, "_FEIGE_FD_DISPATCH_REG", {})
    monkeypatch.setattr(fd, "_FEIGE_FD_DISPATCH_REG_BY_SHOP", {})
    monkeypatch.setattr(fd, "_SHARED_STORE_WARNED", set())
    return ws, fd, sc, bh


def test_placeholder_folder_alone_makes_two_stores_one(shop_mods):
    _, _, sc, _ = shop_mods
    # The bug: without the run identity both attached sessions share a key.
    assert sc.shop_key_of(_session(52271)) == sc.shop_key_of(_session(61926))


def test_run_identity_tells_the_stores_apart(shop_mods):
    _, _, sc, bh = shop_mods
    a, b = _session(52271), _session(61926)
    bh.note_session_identity(a, _state("douyin-6a4b2c53-login", r"C:\ecan_browser_data\douyin-6a4b2c53-login_ea9219"))
    bh.note_session_identity(b, _state("douyin-167bb80f-login", r"C:\ecan_browser_data\douyin-167bb80f-login_ea9219"))
    ka, kb = sc.shop_key_of(a), sc.shop_key_of(b)
    assert ka != kb and "douyin-6a4b2c53" in ka and "douyin-167bb80f" in kb
    # stamped once: a later run cannot re-key a live session
    bh.note_session_identity(a, _state("other"))
    assert sc.shop_key_of(a) == ka
    # profile id alone is enough
    c = _session(9999)
    bh.note_session_identity(c, _state("douyin-x"))
    assert sc.shop_key_of(c) == "profile:fp-douyin-x"
    # no identity in the run: unchanged behaviour
    d = _session(1111)
    bh.note_session_identity(d, {})
    assert not hasattr(d, "_ecan_shop_key")


def test_each_store_s_messages_run_as_its_own_front_desk(shop_mods):
    ws, fd, sc, bh = shop_mods
    a, b = _session(52271), _session(61926)
    bh.note_session_identity(a, _state("douyin-6a4b2c53-login"))
    bh.note_session_identity(b, _state("douyin-167bb80f-login"))
    ctx_a = SimpleNamespace(calling_agent_id="agent_71933829f6944977")   # 前台-抖音二号
    ctx_b = SimpleNamespace(calling_agent_id="agent_d5db329edc314a11")   # 前台-抖音三号
    # front desks register (before_run_hook), store 二号 first
    fd._set_fd_slot(ws.register_shop(sc.shop_key_of(a)), ("cfg", ctx_a, None))
    fd._set_fd_slot(ws.register_shop(sc.shop_key_of(b)), ("cfg", ctx_b, None))
    # WS observers tag each item with their browser's shop (ws_observer._shared_dispatch)
    shop_a = ws.register_shop(sc.shop_key_of(a))
    shop_b = ws.register_shop(sc.shop_key_of(b))
    assert fd._fd_slot(shop_a)[1].calling_agent_id == "agent_71933829f6944977"
    assert fd._fd_slot(shop_b)[1].calling_agent_id == "agent_d5db329edc314a11"


def test_two_front_desks_on_one_store_are_reported(shop_mods, monkeypatch):
    _, fd, _, _ = shop_mods
    warned = []
    monkeypatch.setattr(fd.logger, "warning", lambda msg, *a, **k: warned.append(msg))
    fd._set_fd_slot("", ("cfg", SimpleNamespace(calling_agent_id="agent_A"), object()))
    fd._set_fd_slot("", ("cfg", SimpleNamespace(calling_agent_id="agent_B"), object()))
    assert any("two front desks serve the same store" in m for m in warned)


def test_replies_are_never_redistributed():
    ct = importlib.import_module("agent.mcp.server.chat_utils.chat_tools")
    assert ct._is_reply_payload('{"customer_id": "c", "response_text": "您好"}')
    assert not ct._is_reply_payload('{"customer_id": "c", "latest_message": "在吗"}')   # work handed out
    assert not ct._is_reply_payload('{"response_text": "  "}')
    assert not ct._is_reply_payload("plain text")
