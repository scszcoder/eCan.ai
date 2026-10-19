"""A WeChat QR user is signed back in at startup from the saved 30-day session
token, so an unattended PC comes back without a QR scan. Expired / missing
tokens and non-WeChat users are not restored; a restored session is never
'refreshed' by the token loop (there is nothing to refresh)."""
import base64
import json
import time
from types import SimpleNamespace

import pytest

from auth.auth_manager import AuthManager


def _jwt(exp):
    enc = lambda v: base64.urlsafe_b64encode(json.dumps(v).encode()).rstrip(b"=").decode()
    return f"{enc({'alg': 'HS256'})}.{enc({'sub': 'o3YB', 'exp': exp})}.sig"


def _am(username, token, cn=True):
    am = object.__new__(AuthManager)
    am._is_cn = cn
    am.signed_in = False
    am.tokens = None
    am.current_user = None
    am.user_profile = {}
    am._get_saved_username = lambda: username
    am._get_wechat_session_token = lambda: (bool(token), token or "")
    return am


@pytest.fixture(autouse=True)
def _no_supervisor(monkeypatch):
    import auth.session_supervisor as ss
    calls = []
    monkeypatch.setattr(ss, "get_session_supervisor",
                        lambda: SimpleNamespace(notify_token_installed=lambda: calls.append(1)))
    return calls


def test_wechat_user_with_a_valid_session_token_is_restored(_no_supervisor):
    tok = _jwt(int(time.time()) + 20 * 86400)
    am = _am("wechat_o3YB", tok)
    assert am.try_restore_wechat_session() is True
    assert am.signed_in and am.current_user == "wechat_o3YB"
    assert am.tokens["AccessToken"] == tok and am.tokens["Source"] == "session_restore"
    assert am.user_profile["login_type"] == "wechat"
    assert _no_supervisor == [1]                                  # supervisor told
    assert am._wx_access_token_refreshable() is False             # loop leaves it alone


def test_expired_or_missing_token_or_non_wechat_user_is_not_restored():
    assert _am("wechat_o3YB", _jwt(int(time.time()) - 10)).try_restore_wechat_session() is False
    assert _am("wechat_o3YB", None).try_restore_wechat_session() is False
    assert _am("someone@example.com", _jwt(int(time.time()) + 86400)).try_restore_wechat_session() is False
    assert _am("wechat_o3YB", _jwt(int(time.time()) + 86400), cn=False).try_restore_wechat_session() is False
    am = _am("wechat_o3YB", None)
    am.try_restore_wechat_session()
    assert am.signed_in is False


def test_resume_handler_answers_from_the_restored_session(monkeypatch):
    from gui.ipc.w2p_handlers import cloudbase_handler as ch
    from app_context import AppContext
    am = _am("wechat_o3YB", _jwt(int(time.time()) + 86400))
    am.get_user_profile = lambda: am.user_profile
    am.get_current_user = lambda: am.current_user
    am.is_signed_in = lambda: am.signed_in
    req = {"id": "r", "type": "request", "method": "cloudbase_resume_session", "params": {}}

    monkeypatch.setattr(AppContext, "get_login", staticmethod(lambda: SimpleNamespace(auth_manager=am)))
    monkeypatch.setattr(AppContext, "get_main_window", staticmethod(lambda: object()))   # no launch
    resp = ch.handle_cloudbase_resume_session(req, {})
    assert resp["status"] == "success" and resp["result"]["resumed"] is False   # not signed in yet

    am.try_restore_wechat_session()
    resp = ch.handle_cloudbase_resume_session(req, {})
    r = resp["result"]
    assert r["resumed"] is True and r["token"] and r["user_info"]["username"] == "wechat_o3YB"
    assert r["user_info"]["login_type"] == "wechat"
