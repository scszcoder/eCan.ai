"""Only the app's own login may restore the CloudBase session.

A restore spends the stored refresh token (single-use) and persists the rotated one, so
every extra restoring AuthManager left the live session holding a dead token: its first
refresh ~2 h later failed and the app logged out (customer 11-05).
"""
from unittest import mock

import pytest

import auth.auth_manager as am


@pytest.fixture
def cn(tmp_path, monkeypatch):
    monkeypatch.setattr(am, "_is_cn", lambda: True)
    monkeypatch.setattr(am, "getECBotDataHome", lambda: str(tmp_path))
    monkeypatch.setattr("auth.tencent.cloudbase_adapter.get_cloudbase_adapter", lambda: object())
    calls = []
    monkeypatch.setattr(am.AuthManager, "try_restore_cloudbase_session", lambda self: calls.append("cb") or False)
    monkeypatch.setattr(am.AuthManager, "try_restore_wechat_session", lambda self: calls.append("wx") or False)
    return calls


def test_main_login_restores(cn):
    am.AuthManager()
    assert cn == ["cb", "wx"]


def test_helper_does_not_restore(cn):
    am.AuthManager(restore_session=False)
    assert cn == []


def test_wechat_http_token_helper_does_not_restore(cn, monkeypatch):
    from agent.cloud_api import cloud_api
    monkeypatch.setattr(cloud_api, "_wechat_session_auth_mgr", None)
    monkeypatch.setattr(am.AuthManager, "_get_wechat_session_token", lambda self: (True, "tok"))
    assert cloud_api._get_wechat_http_session_token() == "tok"
    assert cn == []


def test_appsync_token_uses_live_login(cn, monkeypatch):
    from gui.ipc import appsync_subscription_client as sub
    live = mock.Mock()
    live.auth_manager.get_tokens.return_value = None
    monkeypatch.setattr("app_context.AppContext.get_login", staticmethod(lambda: live))
    sub._get_cloudbase_token()
    live.auth_manager.get_tokens.assert_called_once()
    assert cn == []
