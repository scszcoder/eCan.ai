"""Regression coverage for CloudBase access-token expiry.

The 10-minute CloudBase access token may expire while the independently
signed 30-day WeChat session token remains valid. That condition must retain
the signed-in state and continue authenticating HTTP and WebSocket requests
with the durable session token.
"""

from types import SimpleNamespace


def _session_supervisor_module():
    import importlib

    return importlib.import_module("auth.session_supervisor")


def test_supervisor_prefers_durable_cn_session_token():
    """CN consumers receive the durable session JWT before a short access JWT."""
    supervisor_module = _session_supervisor_module()

    class AuthManager:
        signed_in = True
        _is_cn = True
        tokens = {"AccessToken": "expired-cloudbase-token"}

        @staticmethod
        def _get_wechat_session_token():
            return True, "durable-ecan-session-token"

    supervisor = supervisor_module.SessionSupervisor(AuthManager())

    assert supervisor.get_valid_token() == "durable-ecan-session-token"


def test_wx_access_expiry_preserves_durable_session(monkeypatch):
    """WX_TOKEN_EXPIRED defers refreshes rather than clearing the session."""
    supervisor_module = _session_supervisor_module()
    deleted = []

    class AuthManager:
        signed_in = True
        _is_cn = True
        tokens = {"AccessToken": "expired-cloudbase-token"}

        @staticmethod
        def _get_wechat_session_token():
            return True, "durable-ecan-session-token"

        @staticmethod
        def _refresh_wechat_token(_session_token):
            return False, {"code": "WX_TOKEN_EXPIRED", "error": "expired"}

        @staticmethod
        def _delete_wechat_session_token():
            deleted.append(True)

    supervisor = supervisor_module.SessionSupervisor(AuthManager())
    monkeypatch.setattr(supervisor_module.time, "monotonic", lambda: 100.0)

    assert supervisor._attempt_wechat_session_token_refresh() is False
    assert deleted == []
    assert supervisor._am.signed_in is True
    assert supervisor._silent_refresh_next_attempt == (
        100.0 + supervisor.WECHAT_ACCESS_REFRESH_RETRY_SECONDS
    )


def test_auth_manager_keeps_session_signed_in_when_only_access_token_expires():
    """The legacy ensure-valid path must not delete the durable session JWT."""
    import base64
    import json
    import time
    from auth.auth_manager import AuthManager

    def jwt_with_expiry(expiry):
        encode = lambda value: base64.urlsafe_b64encode(
            json.dumps(value).encode()
        ).rstrip(b"=").decode()
        return f"{encode({'alg': 'none'})}.{encode({'exp': expiry})}.signature"

    auth_manager = object.__new__(AuthManager)
    auth_manager._is_cn = True
    auth_manager.signed_in = True
    auth_manager.tokens = {"AccessToken": jwt_with_expiry(int(time.time()) - 1)}
    auth_manager._get_wechat_session_token = lambda: (True, "durable-session")
    auth_manager._refresh_wechat_token = lambda _token: (
        False,
        {"code": "WX_TOKEN_EXPIRED", "error": "expired"},
    )
    auth_manager._delete_wechat_session_token = lambda: (_ for _ in ()).throw(
        AssertionError("durable session must not be deleted")
    )

    assert auth_manager.ensure_valid_tokens() is True
    assert auth_manager.signed_in is True