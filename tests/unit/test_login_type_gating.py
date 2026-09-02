"""
Tests for the login-type gating fix in get_saved_login_info.

Bug: "微信/手机号登录成功后再次进入登录页，邮箱输入框被填充成
wechat id / 手机号" — caused by:

1. uli.json's "user" field stored a synthetic identifier (e.g.
   "wechat_xxx@local" or "13800138000") for non-password logins,
   and get_saved_login_info blindly returned this as the "username"
   field in the IPC response.  The frontend rendered it in the email field.

2. handleTabChange was bypassed when useEffect called setActiveTab directly,
   leaving stale form fields from the previous login type in the Form store.

Fix: get_saved_login_info only returns username/password when
login_type=="password".  For other login types it returns
last_identifier=the_raw_user for debugging but username="".  The frontend
then explicitly resets cross-tab fields after calling setActiveTab.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakeAcctFile:
    """Context-manager that fakes the acct_file on disk for AuthManager."""

    def __init__(self, path: Path, data: dict):
        self._path = path
        self._data = data

    def __enter__(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._data, f)
        return self

    def __exit__(self, *args):
        if self._path.exists():
            self._path.unlink()


def _make_manager(acct_file: Path, acct_data: dict) -> "AuthManager":
    """Build a minimally-configured AuthManager backed by a fake acct_file."""
    from auth.auth_manager import AuthManager

    am = AuthManager.__new__(AuthManager)
    am._is_cn = False
    am.cognito_service = MagicMock()
    am.acct_file = str(acct_file)
    am.ecb_data_homepath = str(acct_file.parent)
    am.machine_role = "Commander"
    am.current_user = None
    am.tokens = None
    am.user_profile = {}
    am.signed_in = False
    am.start_refresh_task = MagicMock()
    am._store_refresh_token = MagicMock()
    am._store_refresh_token_file = MagicMock()
    # Write the fake acct_file so get_saved_login_info can read it
    acct_file.parent.mkdir(parents=True, exist_ok=True)
    with open(acct_file, "w", encoding="utf-8") as f:
        json.dump(acct_data, f)
    return am


# ---------------------------------------------------------------------------
# get_saved_login_info — login_type gating
# ---------------------------------------------------------------------------

class TestGetSavedLoginInfoGating:
    """Verify get_saved_login_info only exposes credentials for password-login."""

    def test_password_login_returns_username_and_password(self, tmp_path: Path):
        """When login_type==password the username and password are returned."""
        from auth.auth_manager import AuthManager

        acct = tmp_path / "uli.json"
        am = _make_manager(acct, {"user": "alice@example.com", "machine_role": "Commander", "login_type": "password"})

        with patch.object(am, "_get_credentials", return_value=(True, "Secret123!")):
            result = am.get_saved_login_info()

        assert result["username"] == "alice@example.com"
        assert result["password"] == "Secret123!"
        assert result["login_type"] == "password"
        assert result["last_identifier"] == "alice@example.com"

    def test_wechat_login_returns_empty_username(self, tmp_path: Path):
        """When login_type==wechat, username/password are blank."""
        from auth.auth_manager import AuthManager

        acct = tmp_path / "uli.json"
        am = _make_manager(
            acct, {"user": "wechat_abc123@local", "machine_role": "Commander", "login_type": "wechat"}
        )

        with patch.object(am, "_get_credentials") as mock_creds:
            result = am.get_saved_login_info()
            # _get_credentials must NOT be called for non-password logins
            mock_creds.assert_not_called()

        assert result["username"] == ""
        assert result["password"] == ""
        assert result["login_type"] == "wechat"
        assert result["last_identifier"] == "wechat_abc123@local"

    def test_phone_login_returns_empty_credentials(self, tmp_path: Path):
        """When login_type==phone, username/password are blank."""
        from auth.auth_manager import AuthManager

        acct = tmp_path / "uli.json"
        am = _make_manager(acct, {"user": "13812345678", "machine_role": "Commander", "login_type": "phone"})

        with patch.object(am, "_get_credentials") as mock_creds:
            result = am.get_saved_login_info()
            mock_creds.assert_not_called()

        assert result["username"] == ""
        assert result["password"] == ""
        assert result["login_type"] == "phone"
        assert result["last_identifier"] == "13812345678"

    def test_google_login_returns_empty_credentials(self, tmp_path: Path):
        """When login_type==google, username/password are blank."""
        from auth.auth_manager import AuthManager

        acct = tmp_path / "uli.json"
        am = _make_manager(acct, {"user": "bob@gmail.com", "machine_role": "Commander", "login_type": "google"})

        with patch.object(am, "_get_credentials") as mock_creds:
            result = am.get_saved_login_info()
            mock_creds.assert_not_called()

        assert result["username"] == ""
        assert result["password"] == ""
        assert result["login_type"] == "google"
        assert result["last_identifier"] == "bob@gmail.com"

    def test_missing_login_type_infers_password_from_stored_credential(self, tmp_path: Path):
        """When login_type is absent (several save paths never stamped it),
        the keyring decides: a NON-EMPTY stored secret means the last login
        was a password login, so credentials prefill (2026-09-02 fix for
        'remember password shows blank fields'). Wechat/OTP identities never
        store a secret, so they still come back blank."""
        from auth.auth_manager import AuthManager

        acct = tmp_path / "uli.json"
        am = _make_manager(acct, {"user": "someone@old.com", "machine_role": "Commander"})

        with patch.object(am, "_get_credentials",
                          return_value=(True, "s3cret")) as mock_creds:
            result = am.get_saved_login_info()
            mock_creds.assert_called_once_with("someone@old.com")

        assert result["username"] == "someone@old.com"
        assert result["password"] == "s3cret"
        assert result["login_type"] == "password"
        assert result["last_identifier"] == "someone@old.com"

    def test_missing_login_type_without_stored_secret_stays_blank(self, tmp_path: Path):
        """No login_type AND no stored secret → blank for safety (an OAuth
        identity like wechat_xxx@local must never prefill the email form)."""
        from auth.auth_manager import AuthManager

        acct = tmp_path / "uli.json"
        am = _make_manager(acct, {"user": "wechat_zzz@local", "machine_role": "Commander"})

        with patch.object(am, "_get_credentials", return_value=(False, "not found")):
            result = am.get_saved_login_info()

        assert result["username"] == ""
        assert result["password"] == ""
        assert result["login_type"] is None
        assert result["last_identifier"] == "wechat_zzz@local"


# ---------------------------------------------------------------------------
# _update_saved_login_info — login_type persistence
# ---------------------------------------------------------------------------

class TestUpdateSavedLoginInfoPersistsLoginType:
    """Verify _update_saved_login_info writes login_type to uli.json."""

    def test_saves_login_type_wechat(self, tmp_path: Path):
        from auth.auth_manager import AuthManager

        acct = tmp_path / "uli.json"
        am = _make_manager(acct, {})

        with patch.object(am, "_store_credentials", return_value=True):
            result = am._update_saved_login_info(
                username="wechat_abc@local", password="", role="Commander", login_type="wechat"
            )

        assert result is True
        with open(acct, encoding="utf-8") as f:
            data = json.load(f)
        assert data["login_type"] == "wechat"
        assert data["user"] == "wechat_abc@local"

    def test_saves_login_type_google(self, tmp_path: Path):
        from auth.auth_manager import AuthManager

        acct = tmp_path / "uli.json"
        am = _make_manager(acct, {})

        with patch.object(am, "_store_credentials", return_value=True):
            am._update_saved_login_info(username="bob@gmail.com", password="", role="Commander", login_type="google")

        with open(acct, encoding="utf-8") as f:
            data = json.load(f)
        assert data["login_type"] == "google"

    def test_saves_login_type_phone(self, tmp_path: Path):
        from auth.auth_manager import AuthManager

        acct = tmp_path / "uli.json"
        am = _make_manager(acct, {})

        with patch.object(am, "_store_credentials", return_value=True):
            am._update_saved_login_info(username="13912345678", password="", role="Platoon", login_type="phone")

        with open(acct, encoding="utf-8") as f:
            data = json.load(f)
        assert data["login_type"] == "phone"
        assert data["user"] == "13912345678"
        assert data["machine_role"] == "Platoon"


# ---------------------------------------------------------------------------
# complete_login_from_provider — passes login_type through
# ---------------------------------------------------------------------------

class TestCompleteLoginFromProviderPassesLoginType:
    """Verify complete_login_from_provider forwards login_type to uli.json."""

    def _manager(self, acct: Path):
        from auth.auth_manager import AuthManager

        am = AuthManager.__new__(AuthManager)
        am._is_cn = True
        am.cognito_service = MagicMock()
        am.acct_file = str(acct)
        am.ecb_data_homepath = str(acct.parent)
        am.machine_role = "Commander"
        am.current_user = None
        am.tokens = None
        am.user_profile = {}
        am.signed_in = False
        am.start_refresh_task = MagicMock()
        am._store_refresh_token = MagicMock()
        am._store_refresh_token_file = MagicMock()
        return am

    def test_wechat_login_type_written_to_uli(self, tmp_path: Path):
        from auth.auth_manager import AuthManager

        acct = tmp_path / "uli.json"
        am = self._manager(acct)

        with patch.object(am, "_update_saved_login_info") as mock_save, patch.object(
            am,
            "_cn_fetch_user_profile",
            return_value=({"openid": "abc123"}, "wechat_abc@local"),
        ):
            am.complete_login_from_provider(
                access_token="fake_access_token",
                refresh_token=None,
                user_identifier="wechat_abc@local",
                user_profile={"login_type": "wechat", "username": "wechat_abc@local"},
            )

        mock_save.assert_called_once()
        _, kwargs = mock_save.call_args
        assert kwargs["login_type"] == "wechat"
        assert kwargs["username"] == "wechat_abc@local"
        assert kwargs["password"] == ""

    def test_phone_login_type_written_via_user_profile(self, tmp_path: Path):
        from auth.auth_manager import AuthManager

        acct = tmp_path / "uli.json"
        am = self._manager(acct)

        with patch.object(am, "_update_saved_login_info") as mock_save, patch.object(
            am, "_cn_fetch_user_profile", return_value=({"phone_number": "13912345678"}, "13912345678")
        ):
            am.complete_login_from_provider(
                access_token="fake_at",
                refresh_token=None,
                user_identifier="13912345678",
                user_profile={"login_type": "phone", "phone_number": "13912345678"},
            )

        _, kwargs = mock_save.call_args
        assert kwargs["login_type"] == "phone"
        assert kwargs["password"] == ""

    def test_explicit_login_type_param_overrides(self, tmp_path: Path):
        """Explicit login_type parameter should be used even if user_profile has one."""
        from auth.auth_manager import AuthManager

        acct = tmp_path / "uli.json"
        am = self._manager(acct)

        with patch.object(am, "_update_saved_login_info") as mock_save, patch.object(
            am, "_cn_fetch_user_profile", return_value=({}, None)
        ):
            am.complete_login_from_provider(
                access_token="at",
                refresh_token=None,
                user_identifier="u@x.com",
                user_profile={"login_type": "google"},  # profile has google
                login_type="wechat",  # but explicit param says wechat
            )

        _, kwargs = mock_save.call_args
        assert kwargs["login_type"] == "wechat"


# ---------------------------------------------------------------------------
# Integration: write-through round-trip (真实写文件，再用新实例读回来)
# ---------------------------------------------------------------------------

class TestLoginTypeGatingWriteThrough:
    """Write to uli.json using _update_saved_login_info, then read back."""

    def test_wechat_write_then_read_hides_credentials(self, tmp_path: Path):
        """WeChat login writes login_type=wechat; next launch get_saved_login_info hides it."""
        from auth.auth_manager import AuthManager

        acct = tmp_path / "uli.json"

        # Step 1: write as complete_login_from_provider would
        am1 = _make_manager(acct, {"user": "wechat_wx_abc@local", "machine_role": "Commander"})
        with patch.object(am1, "_store_credentials", return_value=True):
            am1._update_saved_login_info(
                username="wechat_wx_abc@local",
                password="",
                role="Commander",
                login_type="wechat",
            )

        # Verify file on disk
        with open(acct, encoding="utf-8") as f:
            saved = json.load(f)
        assert saved["user"] == "wechat_wx_abc@local"
        assert saved["login_type"] == "wechat"

        # Step 2: read back as get_saved_login_info would on next launch
        am2 = _make_manager(acct, {"user": "wechat_wx_abc@local", "machine_role": "Commander", "login_type": "wechat"})
        with patch.object(am2, "_get_credentials") as mock_creds:
            result = am2.get_saved_login_info()

        # CRITICAL: email field must NOT be filled with the wechat id
        assert result["username"] == ""
        assert result["password"] == ""
        assert result["login_type"] == "wechat"
        assert result["last_identifier"] == "wechat_wx_abc@local"
        mock_creds.assert_not_called()

    def test_phone_write_then_read_hides_phone_number(self, tmp_path: Path):
        """Phone login writes login_type=phone; next launch hides phone from email field."""
        from auth.auth_manager import AuthManager

        acct = tmp_path / "uli.json"

        am1 = _make_manager(acct, {"user": "13912345678", "machine_role": "Commander"})
        with patch.object(am1, "_store_credentials", return_value=True):
            am1._update_saved_login_info(
                username="13912345678", password="", role="Platoon", login_type="phone"
            )

        with open(acct, encoding="utf-8") as f:
            saved = json.load(f)
        assert saved["login_type"] == "phone"
        assert saved["user"] == "13912345678"

        am2 = _make_manager(acct, {"user": "13912345678", "machine_role": "Platoon", "login_type": "phone"})
        with patch.object(am2, "_get_credentials") as mock_creds:
            result = am2.get_saved_login_info()

        assert result["username"] == ""
        assert result["password"] == ""
        assert result["login_type"] == "phone"
        assert result["last_identifier"] == "13912345678"
        mock_creds.assert_not_called()

    def test_password_write_then_read_exposes_credentials(self, tmp_path: Path):
        """Password login writes login_type=password; next launch exposes credentials."""
        from auth.auth_manager import AuthManager

        acct = tmp_path / "uli.json"

        am1 = _make_manager(acct, {"user": "alice@example.com", "machine_role": "Commander"})
        with patch.object(am1, "_store_credentials", return_value=True):
            am1._update_saved_login_info(
                username="alice@example.com", password="Secret123!", role="Commander", login_type="password"
            )

        with open(acct, encoding="utf-8") as f:
            saved = json.load(f)
        assert saved["login_type"] == "password"
        assert saved["user"] == "alice@example.com"

        am2 = _make_manager(acct, {"user": "alice@example.com", "machine_role": "Commander", "login_type": "password"})
        with patch.object(am2, "_get_credentials", return_value=(True, "Secret123!")):
            result = am2.get_saved_login_info()

        assert result["username"] == "alice@example.com"
        assert result["password"] == "Secret123!"
        assert result["login_type"] == "password"
        assert result["last_identifier"] == "alice@example.com"
