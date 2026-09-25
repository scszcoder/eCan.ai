"""Several Feige shops (store logins, one Chrome each) in ONE process.

A reply, a placeholder, a WS frame or a typing-lock slot must never cross into
another shop's page; with a single shop everything behaves as before.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
    placeholder_timer as pt,
    shop_scope,
    tab_pool,
    typing_lock as tl,
    ws_raw_sender as wsr,
    ws_session as ws,
)
from agent.ec_skills.browser_use_extension.hooks.external.feige_chat.ws_reader import CustomerMessage


def _browser(port, profile=None):
    return SimpleNamespace(cdp_url=f"http://127.0.0.1:{port}",
                           browser_profile=SimpleNamespace(user_data_dir=profile, cdp_url=None))


A, B = _browser(9301, "C:/p/shopA"), _browser(9302, "C:/p/shopB")


@pytest.fixture(autouse=True)
def _clean():
    def reset():
        ws._first_shop[0] = ""
        ws._shops.clear()
        ws._shop_by_talk.clear()
        ws._routing.clear()
        ws._templates.clear()
        ws._talk_to_name.clear()
        ws._session_template = None
        ws._dispatch_live = False
        tab_pool._SHOP_POOLS.clear()
        wsr._shop_copies.clear()
        tl.reset()
    reset()
    yield
    reset()


def _frame(talk, name):
    """A received customer frame (decoded by a patched reader)."""
    return CustomerMessage(customer_name=name, conversation_id=talk, text="hi", ts_ms=1, msg_id="m",
                           sender_role="1", msg_type="text")


def _recv(shop, talk, name):
    with patch.object(ws.ws_reader, "extract_messages", return_value=[_frame(talk, name)]):
        ws.note_recv_frame(b"x", shop)


def _sent(shop, talk):
    with patch.object(ws.ws_sender, "is_read_ack", return_value=False), \
         patch.object(ws.ws_sender, "frame_text", return_value="t"), \
         patch.object(ws.ws_sender, "sent_talk", return_value=talk):
        ws.note_sent_frame(b"TPL-" + talk.encode(), shop)


def _build(tmpl, *, text, client_msg_id):
    return tmpl + b"|" + text.encode()


class TestShopKeys:
    def test_a_shop_is_its_profile_folder_so_a_new_port_is_the_same_shop(self):
        again = _browser(9555, "C:/p/shopA")
        assert shop_scope.shop_key_of(A) == shop_scope.shop_key_of(again)
        assert shop_scope.shop_key_of(A) != shop_scope.shop_key_of(B)

    def test_without_a_profile_folder_the_cdp_endpoint_names_it(self):
        s = SimpleNamespace(cdp_url="ws://localhost:9228/devtools/browser/x", browser_profile=None)
        assert shop_scope.shop_key_of(s) == "127.0.0.1:9228"


class TestOneShopIsUnchanged:
    def test_the_first_shop_uses_the_module_state(self):
        _recv(A, "t1", "小王")
        assert ws._routing == {"小王": "t1"}          # the very dicts tests and logs read
        assert ws.talk_for_name("小王") == "t1"        # callers naming no shop still resolve
        assert tab_pool.get_pool() is tab_pool.get_pool(A)


class TestTwoShops:
    def test_routing_and_send_donors_stay_with_their_shop(self):
        _recv(A, "ta", "小王")
        _recv(B, "tb", "小李")
        _sent(A, "ta")
        _sent(B, "tb")
        assert ws.talk_for_name("小李") == "tb" and ws.talk_for_name("小王") == "ta"
        with patch.object(ws.ws_sender, "build_send_frame", side_effect=_build):
            frame, _cid = ws.frame_for("小李", "ok", shop=B)
        assert frame.startswith(b"TPL-tb")

    def test_a_nickname_both_shops_know_is_never_guessed(self):
        _recv(A, "ta", "同名")
        _recv(B, "tb", "同名")
        _sent(A, "ta")
        _sent(B, "tb")
        assert ws.talk_for_name("同名") == ""
        assert ws.frame_for("同名", "x") is None                     # no shop named: DOM fallback
        with patch.object(ws.ws_sender, "build_send_frame", side_effect=_build):
            assert ws.frame_for("同名", "x", shop=A)[0].startswith(b"TPL-ta")
            assert ws.frame_for("同名", "x", shop=B)[0].startswith(b"TPL-tb")

    def test_another_shops_conversation_is_refused(self):
        _recv(A, "ta", "小王")
        _recv(B, "tb", "小李")
        _sent(B, "tb")
        ws.bind_talk_name("tb2", "小李", shop=A)          # a wrong bind into shop A's routing
        ws._shop_by_talk["tb2"] = shop_scope.shop_key_of(B)
        assert ws.frame_for("小李", "x", shop=A) is None

    def test_dispatch_live_is_per_shop(self):
        _recv(A, "ta", "a")
        _recv(B, "tb", "b")
        ws.set_dispatch_live(True, B)
        assert ws.is_dispatch_live(B) is True
        assert ws.is_dispatch_live(A) is False

    def test_a_second_shop_gets_its_own_raw_socket_and_an_unnamed_send_is_refused(self):
        _recv(A, "ta", "a")
        _recv(B, "tb", "b")
        assert wsr._for_shop(A) is None                   # the first shop: this module
        copy = wsr._for_shop(B)
        assert copy is not None and copy is not wsr and copy._SHOP == ws.resolve_shop(B)
        assert asyncio.run(wsr.raw_send(b"frame")) is False   # which shop? never a guess

    def test_each_shop_has_its_own_pool(self):
        _recv(A, "ta", "a")
        _recv(B, "tb", "b")
        assert tab_pool.get_pool(A) is not tab_pool.get_pool(B)
        assert tab_pool.get_pool() not in (tab_pool.get_pool(A), tab_pool.get_pool(B))


class TestTypingLock:
    def test_shops_type_in_parallel_but_one_page_one_sender(self):
        assert tl.try_acquire("c1", A)
        assert tl.try_acquire("c2", B)
        assert not tl.try_acquire("c3", A)
        assert tl.holder(A) == "c1" and tl.holder(B) == "c2"
        assert not tl.try_acquire("c4")                    # unnamed contends with every shop
        tl.release("c1", A)
        assert tl.try_acquire("c3", A)


class TestPlaceholders:
    def _entry(self, cust, store):
        return pt._TimerEntry(customer_key=cust, source_msg_id="m", armed_at=0.0,
                              deadline_at=0.0, store_key=store)

    def test_each_sweeper_claims_only_its_own_stores_turns(self):
        with pt._REGISTRY_LOCK:
            pt._REGISTRY.clear()
            pt._REGISTRY[("a", "m")] = self._entry("a", "storeA")
            pt._REGISTRY[("b", "m")] = self._entry("b", "storeB")
        try:
            got = pt.claim_expired(max_placeholders=5, rearm_s=10, cap_per_window=0,
                                   accept=lambda e: e.store_key == "storeB")
            assert [e.customer_key for e in got] == ["b"]
        finally:
            with pt._REGISTRY_LOCK:
                pt._REGISTRY.clear()


class TestFrontDeskSlots:
    def test_a_ws_item_goes_to_its_own_shops_front_desk(self):
        from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import front_desk as fd
        _recv(A, "ta", "a")
        _recv(B, "tb", "b")
        fd._set_fd_slot(A, ("cfgA", "ctxA", "agentA"))
        fd._set_fd_slot(B, ("cfgB", "ctxB", "agentB"))
        try:
            assert fd._fd_slot(ws.resolve_shop(B))[2] == "agentB"
            assert fd._fd_slot(ws.resolve_shop(A))[2] == "agentA"
            assert fd._fd_slot("") is None              # unnamed among two shops: not guessed
        finally:
            fd._FEIGE_FD_DISPATCH_REG.pop("slot", None)
            fd._FEIGE_FD_DISPATCH_REG_BY_SHOP.clear()


class TestBrowserCache:
    def test_tasks_sharing_a_skill_in_different_browsers_do_not_share_a_session(self):
        from agent.ec_skills.browser_node.build_helpers import resolve_browser_scope_key
        s1 = {"attributes": {"browser_profile_id": "shopA-login"}}
        s2 = {"attributes": {"browser_profile_id": "shopB-login"}}
        k1 = resolve_browser_scope_key(s1, node_name="monitor")
        k2 = resolve_browser_scope_key(s2, node_name="monitor")
        assert k1 != k2 and k1.startswith("node:monitor")
        assert resolve_browser_scope_key({}, node_name="monitor") == "node:monitor"

    def test_a_reply_finds_the_browser_its_front_desk_runs_in(self):
        from agent.ec_skills.browser_node.build_helpers import note_session_owner, session_owned_by
        note_session_owner(A, "fd-A")
        note_session_owner(B, "fd-B")
        assert session_owned_by(B, "fd-B") and not session_owned_by(A, "fd-B")


class TestPinduoduoStores:
    def test_each_store_has_its_own_reply_box_lock_and_live_socket(self):
        from agent.ec_skills.browser_use_extension.hooks.external.pdd_chat import typing_lock as ptl
        from agent.ec_skills.browser_use_extension.hooks.external.pdd_chat import ws_session as pws
        lock = ptl.TypingLock()
        assert lock.try_acquire("u1", A) and lock.try_acquire("u2", B)
        assert not lock.try_acquire("u3", A)
        assert not lock.try_acquire("u4")                  # unnamed contends with every store
        lock.release("u1", A)
        assert lock.try_acquire("u3", A)
        try:
            pws.set_dispatch_live(True, B)
            assert pws.is_dispatch_live(B) and not pws.is_dispatch_live(A)
        finally:
            pws._live_by_store.clear()
            pws._live = False
