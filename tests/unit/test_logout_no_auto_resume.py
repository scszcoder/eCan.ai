"""Logout took two clicks and ~18 s (2026-10-22): the login page's "resume saved
session" logged straight back in while the logout cleanup was still running,
and the cleanup waited 3 s for EACH of 6 cloud WebSocket threads."""
import threading
import time
import types

import pytest

from agent.cloud_api import cloud_api as ca
from gui.ipc.w2p_handlers import cloudbase_handler as cb


def test_ws_cleanup_waits_once_for_all_threads(monkeypatch):
    stop = threading.Event()
    threads = [threading.Thread(target=stop.wait, daemon=True) for _ in range(6)]
    for t in threads:
        t.start()
    monkeypatch.setattr(ca, "_appsync_ws_threads", list(threads))
    t0 = time.monotonic()
    joined = ca.cleanup_appsync_ws_threads(timeout=0.3)
    took = time.monotonic() - t0
    stop.set()
    assert joined == 0 and took < 1.0, took            # was 6 x 0.3 = 1.8 s


class _AM:
    def __init__(self, user):
        self.user = user

    def is_signed_in(self):
        return True

    def get_current_user(self):
        return self.user

    def get_user_profile(self):
        return {"login_type": "wechat"}


@pytest.fixture
def resume(monkeypatch):
    def call(login):
        import app_context
        monkeypatch.setattr(app_context.AppContext, "get_login", staticmethod(lambda: login))
        monkeypatch.setattr(app_context.AppContext, "get_main_window", staticmethod(lambda: object()))
        monkeypatch.setattr(cb, "create_success_response", lambda req, data: data)
        return cb.handle_cloudbase_resume_session(types.SimpleNamespace(), {"role": "Commander"})
    return call


def test_no_resume_right_after_logout(resume):
    login = types.SimpleNamespace(auth_manager=_AM("wechat_x"),
                                  _logout_requested=(time.monotonic(), "wechat_x"))
    assert resume(login)["resumed"] is False


def test_resume_works_without_a_logout(resume, monkeypatch):
    from gui.ipc import token_manager as tm
    monkeypatch.setattr(tm.token_manager, "generate_token", lambda *a, **k: "tok")
    login = types.SimpleNamespace(auth_manager=_AM("wechat_x"), _logout_requested=None)
    assert resume(login)["resumed"] is True


def test_an_old_logout_does_not_block_a_later_session(resume, monkeypatch):
    from gui.ipc import token_manager as tm
    monkeypatch.setattr(tm.token_manager, "generate_token", lambda *a, **k: "tok")
    long_ago = time.monotonic() - cb._RESUME_BLOCK_AFTER_LOGOUT_S - 5
    login = types.SimpleNamespace(auth_manager=_AM("wechat_x"), _logout_requested=(long_ago, "wechat_x"))
    assert resume(login)["resumed"] is True
