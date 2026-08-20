"""
Unit tests for the CloudBase ↔ Cognito adapter layer.

Verifies that:
1. ``CloudBaseAuthAdapter`` returns Cognito-shape dicts (``success``,
   ``data``, ``error``).
2. Token key normalization is correct (``access_token`` →
   ``AccessToken`` / ``RefreshToken`` / ``ExpiresIn``).
3. ``AuthManager`` CN branches (sign_up_with_otp, phone/email_login_with_otp,
   wechat_login) accept the same dict shape that the Intl surface uses.

These tests stub CloudBaseAuthService so they run offline.
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure ECAN_APP_ID=cn BEFORE any project imports
os.environ.setdefault("ECAN_APP_ID", "cn")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest  # noqa: E402

from auth.tencent.cloudbase_adapter import (  # noqa: E402
    CloudBaseAuthAdapter,
    _normalize_tokens,
    _ok,
    _fail,
)
from auth.tencent.cloudbase_auth import AuthResult  # noqa: E402


# ============================================================
# Shape translation
# ============================================================

class TestTokenNormalization:
    def test_normalize_minimal(self):
        out = _normalize_tokens({
            "access_token": "AT_xxx",
            "refresh_token": "RT_xxx",
            "expires_in": 7200,
            "token_type": "Bearer",
        })
        assert out["AccessToken"] == "AT_xxx"
        assert out["RefreshToken"] == "RT_xxx"
        assert out["ExpiresIn"] == 7200
        assert out["TokenType"] == "Bearer"
        assert out["IdToken"] is None  # CloudBase has no IdToken

    def test_normalize_keeps_user_info(self):
        out = _normalize_tokens({
            "access_token": "AT_xxx",
            "refresh_token": "RT_xxx",
            "user_info": {"sub": "u1", "email": "u@example.com"},
        })
        assert out["UserInfo"]["sub"] == "u1"

    def test_normalize_default_expires(self):
        out = _normalize_tokens({"access_token": "x", "refresh_token": "y"})
        assert out["ExpiresIn"] == 7200

    def test_helpers(self):
        assert _ok({"a": 1}) == {"success": True, "data": {"a": 1}, "error": None}
        assert _fail("oops", "E1") == {
            "success": False, "data": None, "error": "E1", "error_code": "E1"
        }


class TestAdapterMethods:
    """Stub the underlying CloudBaseAuthService and verify adapter contract."""

    def _make(self) -> CloudBaseAuthAdapter:
        adapter = CloudBaseAuthAdapter.__new__(CloudBaseAuthAdapter)
        adapter._service = MagicMock()
        adapter.config = MagicMock()
        adapter.cognito_client = None
        adapter.jwks = None
        return adapter

    def test_login_returns_cognito_shape(self):
        adapter = self._make()
        adapter._service.sign_in_with_password.return_value = AuthResult(
            success=True,
            data={
                "access_token": "AT1",
                "refresh_token": "RT1",
                "expires_in": 3600,
                "token_type": "Bearer",
                "user_info": {"sub": "u1", "email": "u@x.com"},
            },
        )
        result = adapter.login("u@x.com", "pw")
        assert result["success"] is True
        assert result["data"]["AccessToken"] == "AT1"
        assert result["data"]["RefreshToken"] == "RT1"
        assert result["data"]["IdToken"] is None

    def test_login_failure(self):
        adapter = self._make()
        adapter._service.sign_in_with_password.return_value = AuthResult(
            success=False, error="bad creds", error_code="INVALID_CREDENTIALS",
        )
        result = adapter.login("u@x.com", "wrong")
        assert result["success"] is False
        assert result["error"] == "INVALID_CREDENTIALS"

    def test_refresh_tokens_normalizes_keys(self):
        adapter = self._make()
        adapter._service.refresh_token.return_value = AuthResult(
            success=True,
            data={"access_token": "AT2", "refresh_token": "RT2", "expires_in": 7200},
        )
        result = adapter.refresh_tokens("RT1")
        assert result["success"] is True
        assert result["data"]["AccessToken"] == "AT2"
        assert result["data"]["RefreshToken"] == "RT2"

    def test_refresh_tokens_fatal_error_mapping(self):
        """CN's INVALID_REFRESH_TOKEN should be mapped to NotAuthorizedException
        so the refresh loop breaks on revoked tokens."""
        adapter = self._make()
        adapter._service.refresh_token.return_value = AuthResult(
            success=False, error="revoked", error_code="INVALID_REFRESH_TOKEN",
        )
        result = adapter.refresh_tokens("RT1")
        assert result["error"] == "NotAuthorizedException"

    def test_verify_token_no_op(self):
        adapter = self._make()
        result = adapter.verify_token("anything")
        assert result["success"] is False
        assert result["error_code"] == "NOT_SUPPORTED_ON_CN"

    def test_get_userinfo_passthrough(self):
        adapter = self._make()
        adapter._service.get_current_user.return_value = AuthResult(
            success=True, data={"sub": "u1", "email": "u@x.com"},
        )
        result = adapter.get_userinfo("AT1")
        assert result["success"] is True
        assert result["data"]["sub"] == "u1"

    def test_get_wechat_qrcode_uri(self):
        adapter = self._make()
        adapter._service.get_wechat_qrcode_link.return_value = AuthResult(
            success=True, data={"uri": "https://open.weixin.qq.com/...", "session_id": "abc"},
        )
        result = adapter.get_wechat_qrcode_uri(state="xyz", redirect_uri="http://localhost:9382/cb")
        assert result["success"] is True
        assert result["data"]["uri"].startswith("https://open.weixin.qq.com/")

    def test_google_methods_disabled_on_cn(self):
        adapter = self._make()
        result = adapter.get_google_login_url("http://localhost/cb")
        assert result["success"] is False
        assert result["error_code"] == "DISABLED"

        result = adapter.exchange_code_for_tokens("code", "http://localhost/cb")
        assert result["success"] is False
        assert result["error_code"] == "DISABLED"


# ============================================================
# AuthManager CN branches
# ============================================================

class TestAuthManagerCNBranches:
    """Verify that ``AuthManager`` CN entry points accept the Cognito-shape
    return dict and persist tokens correctly. Mocks both ``cognito_service``
    (adapter) and the keyring layer.
    """

    def _manager(self):
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
        # Bypass the real ``_persist_cn_login`` so we don't write to
        # keyring on a developer machine.
        m._persist_cn_login = MagicMock()
        m.start_refresh_task = MagicMock()
        m._cn_fetch_user_profile = MagicMock(return_value=({"email": "u@x.com"}, "u@x.com"))
        m._set_saved_username = MagicMock()
        return m

    def test_sign_up_with_otp_success(self):
        from auth.auth_manager import AuthManager
        m = self._manager()
        m.cognito_service.sign_up_with_otp.return_value = {
            "success": True,
            "data": {
                "AccessToken": "AT1", "RefreshToken": "RT1",
                "IdToken": None, "ExpiresIn": 7200, "TokenType": "Bearer",
            },
        }
        result = AuthManager.sign_up_with_otp(
            m,
            email="u@x.com",
            verification_token="VT1",
            username="u",
            password="pw",
        )
        assert result["success"] is True
        assert m.signed_in is True
        assert m.tokens["AccessToken"] == "AT1"
        assert m.current_user == "u@x.com"
        m._persist_cn_login.assert_called_once()
        m.start_refresh_task.assert_called_once()

    def test_sign_up_with_otp_cn_only_guard(self):
        from auth.auth_manager import AuthManager
        m = self._manager()
        m._is_cn = False
        result = AuthManager.sign_up_with_otp(
            m, email="u@x.com", verification_token="VT1",
        )
        assert result["success"] is False
        assert "CN-only" in result["error"]

    def test_phone_login_with_otp(self):
        from auth.auth_manager import AuthManager
        m = self._manager()
        mock_svc = MagicMock()
        mock_svc.sign_in_with_otp.return_value = AuthResult(
            success=True,
            data={
                "access_token": "AT1", "refresh_token": "RT1",
                "expires_in": 7200, "token_type": "Bearer",
            },
        )
        with patch("auth.tencent.cloudbase_auth.get_cloudbase_service", return_value=mock_svc):
            result = AuthManager.phone_login_with_otp(
                m, phone_number="13800138000", verification_token="VT1",
            )
        assert result["success"] is True
        assert m.tokens["AccessToken"] == "AT1"
        assert m.tokens["RefreshToken"] == "RT1"
        m._persist_cn_login.assert_called_once()

    def test_email_login_with_otp_failure(self):
        from auth.auth_manager import AuthManager
        m = self._manager()
        mock_svc = MagicMock()
        mock_svc.sign_in_with_otp.return_value = AuthResult(
            success=False, error="expired", error_code="EXPIRED_CODE",
        )
        with patch("auth.tencent.cloudbase_auth.get_cloudbase_service", return_value=mock_svc):
            result = AuthManager.email_login_with_otp(
                m, email="u@x.com", verification_token="VT1",
            )
        assert result["success"] is False
        assert result["error_code"] == "EXPIRED_CODE"

    def test_wechat_login_returns_error_when_not_cn(self):
        from auth.auth_manager import AuthManager
        m = self._manager()
        m._is_cn = False
        result = AuthManager.wechat_login(m)
        assert result["success"] is False

    def test_wechat_login_bails_when_not_configured(self):
        from auth.auth_manager import AuthManager
        m = self._manager()
        m.cognito_service.config.is_wechat_configured.return_value = False
        result = AuthManager.wechat_login(m)
        assert result["success"] is False
        assert "not configured" in result["error"]

    def test_reset_password_with_otp(self):
        from auth.auth_manager import AuthManager
        m = self._manager()
        m.cognito_service.reset_password_with_otp.return_value = {
            "success": True, "data": {},
        }
        result = AuthManager.reset_password_with_otp(
            m,
            phone_number="13800138000",
            verification_id="VID1",
            verification_code="123456",
            new_password="NewPw123!",
        )
        assert result["success"] is True
        m.cognito_service.reset_password_with_otp.assert_called_once()

    # ============================================================
    # complete_login_from_provider — post-login session installer
    # ============================================================

    class TestCompleteLoginFromProvider:
        """Verify the new ``AuthManager.complete_login_from_provider`` method.

        This is the entry point CN handlers call after the upstream provider
        (CloudBase OTP / WeChat / …) has already returned tokens, so the rest
        of the Intl post-login chain (``Login.handleLogin`` → MainWindow)
        can run identically without re-calling the auth backend.
        """

        def _manager(self):
            from auth.auth_manager import AuthManager
            m = AuthManager.__new__(AuthManager)
            m._is_cn = True
            m.cognito_service = MagicMock()
            m.machine_role = ""
            m.current_user = None
            m.tokens = None
            m.user_profile = {}
            m.signed_in = False
            m.start_refresh_task = MagicMock()
            # complete_login_from_provider now writes the full uli.json
            # (user + machine_role) via ``_update_saved_login_info``,
            # matching the Intl password-login behavior so the frontend's
            # get_last_login returns the right user next time.
            m._update_saved_login_info = MagicMock(return_value=True)
            m._cn_fetch_user_profile = MagicMock(
                return_value=({"email": "u@x.com"}, "u@x.com")
            )
            return m

        def test_installs_tokens_and_marks_signed_in(self):
            from auth.auth_manager import AuthManager
            m = self._manager()
            with patch("keyring.set_password") as mock_kr:
                result = AuthManager.complete_login_from_provider(
                    m,
                    access_token="AT_xxx",
                    refresh_token="RT_xxx",
                    user_identifier="u@x.com",
                    user_profile={"email": "u@x.com"},
                )
            assert result["success"] is True
            assert m.tokens["AccessToken"] == "AT_xxx"
            assert m.tokens["RefreshToken"] == "RT_xxx"
            assert m.tokens["TokenType"] == "Bearer"
            assert m.tokens["ExpiresIn"] == 7200
            assert m.signed_in is True
            assert m.current_user == "u@x.com"
            assert m.user_profile["email"] == "u@x.com"
            m.start_refresh_task.assert_called_once()
            # uli.json update must be called with the new user
            m._update_saved_login_info.assert_called_once()
            args, kwargs = m._update_saved_login_info.call_args
            assert kwargs["username"] == "u@x.com"
            assert kwargs["role"] == "Commander"

        def test_uses_caller_supplied_profile(self):
            from auth.auth_manager import AuthManager
            m = self._manager()
            profile = {
                "email": "real@example.com",
                "name": "Real Name",
                "login_type": "wechat",
            }
            result = AuthManager.complete_login_from_provider(
                m,
                access_token="AT",
                refresh_token="RT",
                user_identifier="real@example.com",
                user_profile=profile,
            )
            assert result["success"] is True
            assert m.user_profile == profile
            # Caller-supplied profile wins for the user_profile dict,
            # but on CN we still decode the access_token JWT to surface
            # the openid claim — without it every WeChat user would
            # collapse onto ``user_identifier`` and silently overwrite
            # the previous WeChat user's keyring entry (see
            # tests/unit/test_cloudbase_wechat_openid_regression.py).
            m._cn_fetch_user_profile.assert_called_once_with("AT")

        def test_falls_back_to_cn_profile_when_missing(self):
            from auth.auth_manager import AuthManager
            m = self._manager()
            result = AuthManager.complete_login_from_provider(
                m,
                access_token="AT",
                refresh_token="RT",
                user_identifier="placeholder",
                user_profile=None,
            )
            assert result["success"] is True
            m._cn_fetch_user_profile.assert_called_once_with("AT")
            assert m.current_user == "u@x.com"  # from cn profile

        def test_persists_refresh_token_to_keyring_cn(self):
            from auth.auth_manager import AuthManager
            m = self._manager()
            with patch("keyring.set_password") as mock_kr:
                AuthManager.complete_login_from_provider(
                    m,
                    access_token="AT",
                    refresh_token="RT_secret",
                    user_identifier="u@x.com",
                    user_profile={"email": "u@x.com"},
                )
            mock_kr.assert_called_once_with(
                "ecan_cloudbase_refresh", "u@x.com", "RT_secret"
            )

        def test_password_login_persists_password_via_keyring(self):
            """For password flows, ``password`` is forwarded through to
            ``_update_saved_login_info`` which writes it to
            ``ecan_cloudbase_auth`` keyring (via ``_store_credentials``).
            For OTP / phone / WeChat flows it's empty string."""
            from auth.auth_manager import AuthManager
            m = self._manager()
            with patch("keyring.set_password") as mock_kr:
                AuthManager.complete_login_from_provider(
                    m,
                    access_token="AT",
                    refresh_token="RT",
                    user_identifier="u@x.com",
                    password="MySecret!",
                    user_profile={"email": "u@x.com"},
                )
            m._update_saved_login_info.assert_called_once_with(
                username="u@x.com", password="MySecret!", role="Commander",
                login_type=None,  # user_profile has no login_type
            )

        def test_swallows_keyring_errors(self):
            from auth.auth_manager import AuthManager
            m = self._manager()
            with patch("keyring.set_password", side_effect=Exception("keyring fail")):
                result = AuthManager.complete_login_from_provider(
                    m,
                    access_token="AT",
                    refresh_token="RT",
                    user_identifier="u@x.com",
                    user_profile={"email": "u@x.com"},
                )
            assert result["success"] is True
            assert m.signed_in is True

        def test_swallows_refresh_task_errors(self):
            """``start_refresh_task`` may need a running event loop. The IPC
            handler must not fail just because one isn't there yet."""
            from auth.auth_manager import AuthManager
            m = self._manager()
            m.start_refresh_task = MagicMock(
                side_effect=Exception("no event loop")
            )
            result = AuthManager.complete_login_from_provider(
                m,
                access_token="AT",
                refresh_token="RT",
                user_identifier="u@x.com",
                user_profile={"email": "u@x.com"},
            )
            assert result["success"] is True

        def test_missing_refresh_token_does_not_crash(self):
            from auth.auth_manager import AuthManager
            m = self._manager()
            with patch("keyring.set_password") as mock_kr:
                result = AuthManager.complete_login_from_provider(
                    m,
                    access_token="AT",
                    refresh_token=None,
                    user_identifier="u@x.com",
                    user_profile={"email": "u@x.com"},
                )
            assert result["success"] is True
            assert m.tokens["RefreshToken"] is None
            mock_kr.assert_not_called()

        def test_custom_expires_in(self):
            from auth.auth_manager import AuthManager
            m = self._manager()
            AuthManager.complete_login_from_provider(
                m,
                access_token="AT",
                refresh_token="RT",
                expires_in=3600,
                user_identifier="u@x.com",
                user_profile={"email": "u@x.com"},
            )
            assert m.tokens["ExpiresIn"] == 3600


if __name__ == "__main__":
    pytest.main([__file__, "-v"])