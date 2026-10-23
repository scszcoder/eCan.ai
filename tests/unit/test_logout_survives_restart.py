"""A deliberate logout must survive a restart.

The bug (2026-10-23): the user clicked "log out", restarted eCan, and was
logged straight back in.

Root cause: ``AuthManager.logout()`` removed the refresh token but left
the credentials the startup restore path actually reads:

  * the 30-day WeChat session token (keyring ``ecan_wechat_session`` +
    the ``.wx_st_*`` file) — read by ``try_restore_wechat_session``,
  * the CN CloudBase refresh token (keyring ``ecan_cloudbase_refresh``)
    — read by ``try_restore_cloudbase_session``,
  * the ``user`` field in ``uli.json`` — the restore path uses it to
    find the credentials in the first place.

So the restore succeeded and signed the user back in.  These tests pin
the whole set, because fixing only one of them still leaves the bug
alive (a password login restores via the CloudBase refresh token; a
QR login restores via the WeChat session token).
"""

import json

import pytest


def _make_auth_manager(tmp_path, monkeypatch, *, user="wechat_openid:abc@local"):
    """An AuthManager with the persisted-credential plumbing redirected
    into tmp_path, so the test never touches the real keyring or the
    real uli.json.
    """
    from auth import auth_manager as am_mod

    acct_file = tmp_path / "uli.json"
    acct_file.write_text(json.dumps({"user": user, "machine_role": "Commander",
                                     "language": "en"}), encoding="utf-8")

    am = object.__new__(am_mod.AuthManager)
    am._is_cn = True
    am.acct_file = str(acct_file)
    am.ecb_data_homepath = str(tmp_path)
    am.tokens = {"AccessToken": "x"}
    am.current_user = user
    am.signed_in = True
    am.user_profile = {"login_type": "wechat"}

    deleted = {"refresh": [], "cloudbase_refresh": [], "wechat_session": []}

    monkeypatch.setattr(am_mod.AuthManager, "_delete_refresh_token",
                        lambda self, u: deleted["refresh"].append(u))
    monkeypatch.setattr(am_mod.AuthManager, "_delete_cloudbase_refresh_token",
                        lambda self, u: deleted["cloudbase_refresh"].append(u))
    monkeypatch.setattr(am_mod.AuthManager, "_delete_wechat_session_token",
                        lambda self: deleted["wechat_session"].append(True))
    monkeypatch.setattr(am_mod.AuthManager, "stop_refresh_task", lambda self: None)
    return am, deleted, acct_file


def test_logout_removes_the_wechat_session_token(tmp_path, monkeypatch):
    """The 30-day session token is what signs a QR user back in."""
    am, deleted, _ = _make_auth_manager(tmp_path, monkeypatch)
    am.logout()
    assert deleted["wechat_session"], "the WeChat session token must be deleted"


def test_logout_removes_the_cloudbase_refresh_token(tmp_path, monkeypatch):
    """The CN refresh token lives in its own keyring service, so the
    generic refresh-token delete does not cover it."""
    am, deleted, _ = _make_auth_manager(tmp_path, monkeypatch)
    am.logout()
    assert deleted["cloudbase_refresh"], "the CN CloudBase refresh token must be deleted"


def test_logout_clears_the_saved_user_but_keeps_the_rest_of_uli_json(tmp_path, monkeypatch):
    """uli.json holds the username the restore path looks up.  Clearing
    only the username keeps the language and the machine role."""
    am, _, acct_file = _make_auth_manager(tmp_path, monkeypatch)
    am.logout()
    data = json.loads(acct_file.read_text(encoding="utf-8"))
    assert "user" not in data
    assert data.get("language") == "en"
    assert data.get("machine_role") == "Commander"


def test_logout_clears_the_in_memory_session(tmp_path, monkeypatch):
    am, _, _ = _make_auth_manager(tmp_path, monkeypatch)
    am.logout()
    assert am.signed_in is False
    assert am.current_user is None
    assert am.tokens is None


def test_a_restart_after_logout_cannot_restore_the_session(tmp_path, monkeypatch):
    """The end-to-end shape of the bug: after logout, the startup restore
    path must find nothing to restore with.
    """
    am, _, acct_file = _make_auth_manager(tmp_path, monkeypatch)
    am.logout()

    # uli.json no longer names a user, so there is nothing to look up.
    assert am._get_saved_username() is None

    # And the session token is gone, so even a remembered username cannot
    # be turned back into a session.
    monkeypatch.setattr(
        am.__class__, "_get_wechat_session_token", lambda self: (False, "no file"))
    assert am.try_restore_wechat_session() is False


def test_logout_keeps_the_saved_password(tmp_path, monkeypatch):
    """Signing out is not signing up: the password stays so the login
    form can pre-fill, and it is useless without the tokens.
    """
    am, _, _ = _make_auth_manager(tmp_path, monkeypatch)
    am.logout()
    # The password lives in the keyring, which logout does not touch.
    assert "ecan_cloudbase_auth" not in getattr(am, "_logout_deleted_services", [])
