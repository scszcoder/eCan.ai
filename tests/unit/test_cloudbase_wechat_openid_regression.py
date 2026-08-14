"""
Regression tests for the CloudBase WeChat restore / refresh-token chain.

Background
----------
Runlog 2026-08-14 19:02: the previous WeChat login wrote its refresh
token to ``keyring`` using ``current_user = "wechat_user@wechat.local"``
(the synthetic fallback when ``_cn_fetch_user_profile`` couldn't extract
an email/phone).  On every subsequent restart ``try_restore_cloudbase_session``
looked up that keyring entry, found nothing (the next WeChat login had
overwritten it with the same synthetic key), and the session was lost.
The user-visible symptom: 401 errors with a token that still claimed
9 minutes of life — the access_token was stale because no refresh was
ever possible.

This file pins three layered fixes:

  1. ``_cn_fetch_user_profile`` extracts the ``openid`` claim from the
     CloudBase access_token JWT and surfaces it as ``user_profile["openid"]``.
  2. WeChat ``complete_login`` uses that real openid in the fallback
     chain, so each WeChat user ends up with a unique ``current_user``
     and therefore a unique keyring key (no silent cross-user overwrite).
  3. ``try_restore_cloudbase_session`` falls back to the encrypted file
     store when the keyring entry is missing, AND ``wechat_login`` /
     ``complete_login`` now write the file fallback when keyring itself
     fails — so a single locked keychain doesn't permanently strand the
     session.
"""

import base64
import json
import os
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# 1. _cn_fetch_user_profile surfaces the openid claim
# ---------------------------------------------------------------------------


def _make_jwt_with_claims(claims: dict) -> str:
    """Build a syntactically valid (unsigned) JWT carrying the given claims.
    Matches ``_decode_jwt_payload_unsafe``'s expectations (it skips
    signature verification anyway)."""
    header = {"alg": "none", "typ": "JWT"}
    payload = dict(claims)
    b64 = lambda d: base64.urlsafe_b64encode(
        json.dumps(d).encode()
    ).rstrip(b"=").decode()
    return f"{b64(header)}.{b64(payload)}.stub"


def test_cn_fetch_user_profile_surfaces_openid_claim():
    """CloudBase WeChat JWTs carry ``openid: openid:<hex>``.  That must be
    copied into ``user_profile["openid"]`` so the WeChat login path can
    use it as a per-user identifier instead of falling through to the
    synthetic ``wechat_user@wechat.local`` (which silently overwrites
    every other WeChat user's keyring entry)."""
    from auth.auth_manager import AuthManager

    m = AuthManager.__new__(AuthManager)
    m.cognito_service = MagicMock()  # /user/me fallback available but unused

    access_token = _make_jwt_with_claims({
        "iss": "cloudbase",
        "sub": "283f7e32-d616-477e-8b75-265607ebaf9e",
        "uid": "283f7e32-d616-477e-8b75-265607ebaf9e",
        "openid": "openid:AABE7F974D8D3866BD2923A07B62324A9D5CB06D9",
        "exp": 9999999999,
    })

    profile, email = m._cn_fetch_user_profile(access_token)

    assert profile.get("openid") == "openid:AABE7F974D8D3866BD2923A07B62324A9D5CB06D9", (
        "_cn_fetch_user_profile must surface the openid claim so WeChat "
        "users get unique current_user values across logins"
    )


# ---------------------------------------------------------------------------
# 2. complete_login uses real openid (not synthetic fallback) for WeChat users
# ---------------------------------------------------------------------------


def test_complete_login_wechat_uses_openid_when_no_email():
    """When WeChat returns no email/phone, ``current_user`` MUST be
    derived from the access_token's ``openid`` claim rather than the
    synthetic ``wechat_user@wechat.local`` string.  Without this every
    WeChat user overwrites every previous WeChat user's keyring entry."""
    from auth.auth_manager import AuthManager

    m = AuthManager.__new__(AuthManager)
    m._is_cn = True
    m.cognito_service = MagicMock()
    m.machine_role = "Commander"
    m.current_user = None
    m.tokens = None
    m.user_profile = {}
    m.signed_in = False
    m.refresh_task = None
    m._persist_cn_login = MagicMock()
    m.start_refresh_task = MagicMock()
    # Simulate a CloudBase WeChat response: no email/phone, but the
    # _cn_fetch_user_profile call returned the openid in user_profile.
    m._cn_fetch_user_profile = MagicMock(return_value=(
        {"openid": "openid:AABE7F974D8D3866BD2923A07B62324A9D5CB06D9",
         "sub": "283f7e32-d616-477e-8b75-265607ebaf9e"},
        None,
    ))
    m._set_saved_username = MagicMock()

    # Stub the keyring write so the test doesn't touch the developer machine.
    with patch("auth.auth_manager.keyring.set_password") as mock_set:
        # Patch _store_refresh_token_file too (called by the keyring-fail
        # fallback we added).
        m._store_refresh_token_file = MagicMock()
        result =             AuthManager.complete_login_from_provider(
                m,
                access_token="AT",
                refresh_token="RT",
                expires_in=7200,
                user_identifier="ignored: complete_login should overwrite",
                role="Commander",
            )

    assert result["success"] is True
    assert m.current_user == "wechat_openid:AABE7F974D8D3866BD2923A07B62324A9D5CB06D9@wechat.local", (
        f"complete_login must derive current_user from the real openid "
        f"so two different WeChat users can't share a keyring entry. "
        f"Got: {m.current_user!r}"
    )
    # And the unique key must reach keyring so a future restore can find it.
    written_keys = [call.args[1] for call in mock_set.call_args_list]
    assert "wechat_openid:AABE7F974D8D3866BD2923A07B62324A9D5CB06D9@wechat.local" in written_keys, (
        f"keyring.set_password must be called with the openid-derived key, "
        f"not the synthetic fallback.  Got keys: {written_keys!r}"
    )


def test_complete_login_wechat_different_openids_dont_collide():
    """Two WeChat logins with different openids MUST produce different
    keyring keys.  The original bug collapsed both onto
    ``wechat_user@wechat.local``, silently overwriting each other."""
    from auth.auth_manager import AuthManager

    OPENID_A = "openid:AAAAAAAAAAAAAAAAAAAA"
    OPENID_B = "openid:BBBBBBBBBBBBBBBBBBBB"

    def _run_one(openid: str) -> str:
        m = AuthManager.__new__(AuthManager)
        m._is_cn = True
        m.cognito_service = MagicMock()
        m.machine_role = "Commander"
        m.current_user = None
        m.tokens = None
        m.user_profile = {}
        m.signed_in = False
        m.refresh_task = None
        m._persist_cn_login = MagicMock()
        m.start_refresh_task = MagicMock()
        m._cn_fetch_user_profile = MagicMock(return_value=(
            {"openid": openid, "sub": "x"}, None,
        ))
        m._set_saved_username = MagicMock()
        with patch("auth.auth_manager.keyring.set_password"):
            m._store_refresh_token_file = MagicMock()
            AuthManager.complete_login_from_provider(
                m, access_token="AT",
                refresh_token="RT", expires_in=7200,
                user_identifier="ignored", role="Commander",
            )
        return m.current_user

    ident_a = _run_one(OPENID_A)
    ident_b = _run_one(OPENID_B)

    assert ident_a != ident_b, (
        f"Two different WeChat users MUST end up with different "
        f"current_user values so their keyring entries don't collide. "
        f"Got ident_a={ident_a!r} ident_b={ident_b!r}"
    )
    assert OPENID_A in ident_a and OPENID_B not in ident_a
    assert OPENID_B in ident_b and OPENID_A not in ident_b


# ---------------------------------------------------------------------------
# 3. try_restore_cloudbase_session falls back to file when keyring is empty
# ---------------------------------------------------------------------------


def test_try_restore_cloudbase_session_recovers_from_file_fallback(monkeypatch):
    """When the keyring entry is missing but the encrypted file fallback
    has the refresh token, ``try_restore_cloudbase_session`` MUST use
    the file token to call CloudBase refresh.  Without this fix a
    one-time keyring failure strands the session until the user
    re-scans the QR (runlog 2026-08-14 19:02)."""
    from auth.auth_manager import AuthManager

    m = AuthManager.__new__(AuthManager)
    m._is_cn = True
    m.tokens = None
    m.signed_in = False
    m.current_user = None
    m.user_profile = {}
    m.machine_role = "Commander"
    m._get_saved_username = MagicMock(return_value="wechat_xx@wechat.local")
    m._setup_token_manager_from_tokens = MagicMock()

    # keyring.get_password: password is there but refresh token is not.
    def fake_get_password(service, key):
        if service == "ecan_cloudbase_auth":
            return "pw"
        return None  # ecan_cloudbase_refresh missing

    # File fallback returns a valid refresh token.
    m._get_refresh_token_file = MagicMock(return_value=(True, "RT_FROM_FILE"))

    refresh_called_with = []

    class _StubService:
        def refresh_token(self, rt):
            refresh_called_with.append(rt)
            return MagicMock(success=True, data={"AccessToken": "NEW_AT"})

    monkeypatch.setattr("auth.auth_manager.keyring.get_password", fake_get_password)
    monkeypatch.setattr(
        "auth.tencent.cloudbase_auth.CloudBaseAuthService",
        lambda *a, **kw: _StubService(),
    )
    m._delete_cloudbase_credentials = MagicMock()

    ok = m.try_restore_cloudbase_session()

    assert ok is True, "restore must succeed when file fallback has the refresh token"
    assert refresh_called_with == ["RT_FROM_FILE"], (
        f"CloudBase refresh_token MUST be called with the file-fallback "
        f"refresh token.  Got: {refresh_called_with!r}"
    )
    m._get_refresh_token_file.assert_called_once()
    # And the restored session must carry both the new AT and the RT
    # so subsequent Supervisor ticks can keep refreshing.
    assert m.tokens["AccessToken"] == "NEW_AT"
    assert m.tokens["RefreshToken"] == "RT_FROM_FILE"
    assert m.signed_in is True


def test_try_restore_cloudbase_session_no_token_either_place_returns_false(monkeypatch):
    """When neither keyring NOR file fallback has the refresh token,
    the function must return False (not crash, not silently succeed
    with stale data)."""
    from auth.auth_manager import AuthManager

    m = AuthManager.__new__(AuthManager)
    m._is_cn = True
    m.tokens = None
    m.signed_in = False
    m.current_user = None
    m.user_profile = {}
    m.machine_role = "Commander"
    m._get_saved_username = MagicMock(return_value="wechat_xx@wechat.local")
    m._setup_token_manager_from_tokens = MagicMock()
    m._get_refresh_token_file = MagicMock(return_value=(False, ""))
    m._delete_cloudbase_credentials = MagicMock()

    monkeypatch.setattr(
        "auth.auth_manager.keyring.get_password",
        lambda service, key: "pw" if service == "ecan_cloudbase_auth" else None,
    )

    assert m.try_restore_cloudbase_session() is False
    assert m.signed_in is False


# ---------------------------------------------------------------------------
# 4. CN keyring-write failures fall back to the encrypted file store
# ---------------------------------------------------------------------------


def test_complete_login_keyring_failure_writes_file_fallback():
    """If ``keyring.set_password`` raises (locked keychain, ``-25244``,
    ``@`` in the service key, etc.), ``complete_login`` MUST still
    persist the refresh token via ``_store_refresh_token_file`` so a
    later ``try_restore_cloudbase_session`` can recover it."""
    from auth.auth_manager import AuthManager

    m = AuthManager.__new__(AuthManager)
    m._is_cn = True
    m.cognito_service = MagicMock()
    m.machine_role = "Commander"
    m.current_user = "u@x.com"
    m.tokens = None
    m.user_profile = {"email": "u@x.com"}
    m.signed_in = False
    m.refresh_task = None
    m._persist_cn_login = MagicMock()
    m.start_refresh_task = MagicMock()
    m._cn_fetch_user_profile = MagicMock(return_value=({"email": "u@x.com"}, "u@x.com"))
    m._set_saved_username = MagicMock()
    m._store_refresh_token_file = MagicMock()

    with patch(
        "auth.auth_manager.keyring.set_password",
        side_effect=Exception("simulated keychain -25244"),
    ):
        result = AuthManager.complete_login_from_provider(
            m,
            access_token="AT",
            refresh_token="RT_THAT_NEEDS_SAVING",
            expires_in=7200,
            user_identifier="u@x.com",
            role="Commander",
        )

    assert result["success"] is True
    m._store_refresh_token_file.assert_called_once_with("u@x.com", "RT_THAT_NEEDS_SAVING"), (
        "When keyring.set_password fails, complete_login MUST persist the "
        "refresh token to the encrypted file fallback. Without this, a "
        "single keychain hiccup strands the user."
    )
