"""A QR login through the unified login callback gives the desktop an opaque
website session token (no dots). The server stores no weChatSession row for it,
so refreshWeChatToken always answers SESSION_EXPIRED "session not found". The
45-minute refresh loop must not sign such a session out (customer 2026-10-18:
signed out at 15:41, bounced to the QR screen at 22:51, though every call kept
working on the 30-day session token). A JWT login still refreshes as before."""
import asyncio

import pytest

from auth import auth_manager as am_mod
from auth.auth_manager import AuthManager


def _manager(access_token, refresh_result):
    am = object.__new__(AuthManager)
    am._is_cn = True
    am.signed_in = True
    am.tokens = {"AccessToken": access_token, "RefreshToken": None}
    am._get_wechat_session_token = lambda: (True, "durable-session")
    am.refresh_calls = 0

    def _refresh(_tok):
        am.refresh_calls += 1
        return refresh_result
    am._refresh_wechat_token = _refresh
    return am


def _run_loop(am, monkeypatch, rounds=3):
    """Run the real loop for a few 45-min rounds with sleep stubbed out."""
    n = {"sleeps": 0}

    async def fake_sleep(_s):
        n["sleeps"] += 1
        if n["sleeps"] > rounds:
            raise asyncio.CancelledError()

    monkeypatch.setattr(am_mod.asyncio, "sleep", fake_sleep)
    try:
        asyncio.run(am._token_refresh_loop())   # the loop treats cancel as "stop"
    except asyncio.CancelledError:
        pass
    assert n["sleeps"] > rounds, "loop ended early instead of waiting for the next round"


def test_opaque_website_token_is_never_refreshed_and_stays_signed_in(monkeypatch):
    am = _manager("Zk3x9QpL0aVb7Yt2Wm5Rn8Hc4Jd6Ue1Sg0Fo3Iq7Pl2",  # 43-char opaque token
                  (False, {"code": "SESSION_EXPIRED", "error": "WeChat session not found"}))
    _run_loop(am, monkeypatch)
    assert am.signed_in is True
    assert am.refresh_calls == 0


class _Sup:
    def __init__(self):
        self.cleared = []

    def notify_session_cleared(self, source=""):
        self.cleared.append(source)


@pytest.fixture
def sup(monkeypatch):
    import auth.session_supervisor as ss
    s = _Sup()
    monkeypatch.setattr(ss, "get_session_supervisor", lambda: s)
    return s


def test_jwt_login_session_expired_still_signs_out_and_tells_the_gui(monkeypatch, sup):
    am = _manager("aaa.bbb.ccc", (False, {"code": "SESSION_EXPIRED", "error": "Session expired"}))
    asyncio.run(_one_round(am, monkeypatch))
    assert am.refresh_calls == 1
    assert am.signed_in is False
    assert sup.cleared == ["refresh_loop_wechat_session_expired"]   # the window gets the logout notice


def test_opaque_login_sends_no_logout_notice(monkeypatch, sup):
    am = _manager("Zk3x9QpL0aVb7Yt2Wm5Rn8Hc4Jd6Ue1Sg0Fo3Iq7Pl2",
                  (False, {"code": "SESSION_EXPIRED", "error": "WeChat session not found"}))
    _run_loop(am, monkeypatch)
    assert sup.cleared == []


def test_jwt_login_refresh_success_installs_token(monkeypatch):
    am = _manager("aaa.bbb.ccc", (True, {"accessToken": "new.jwt.token"}))
    _run_loop(am, monkeypatch, rounds=2)
    assert am.signed_in is True and am.tokens["AccessToken"] == "new.jwt.token"
    assert am.refresh_calls >= 1


async def _one_round(am, monkeypatch):
    async def fake_sleep(_s):
        return None
    monkeypatch.setattr(am_mod.asyncio, "sleep", fake_sleep)
    await am._token_refresh_loop()       # SESSION_EXPIRED breaks the loop
