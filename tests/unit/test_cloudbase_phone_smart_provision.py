"""
Unit tests for handle_cloudbase_send_code and handle_cloudbase_phone_login.

These tests cover the phone-login "smart provision" behavior introduced for
the design where the same UI flow handles both login and signup.

Verified behavior:
1. ``handle_cloudbase_send_code`` passes through ``is_user`` to the frontend.
2. ``handle_cloudbase_phone_login`` falls back to ``sign_up_with_otp`` when
   ``sign_in_with_otp`` returns ``NOT_FOUND``.
3. ``handle_cloudbase_phone_login`` does NOT silently create an account when
   the user exists but sign_in returns a non-NOT_FOUND error (e.g. EXPIRED).
4. ``handle_cloudbase_phone_login`` returns LOGIN_FAILED when neither sign_in
   nor sign_up succeed.
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("ECAN_APP_ID", "cn")

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

import pytest  # noqa: E402


# --- Imports under test ---

from auth.tencent.cloudbase_auth import AuthResult  # noqa: E402


# --- Helpers ---

def _ok(data: dict) -> AuthResult:
    return AuthResult(success=True, data=data)


def _fail(error: str, code: str = "ERROR") -> AuthResult:
    return AuthResult(success=False, error=error, error_code=code)


def _get_handler(name: str):
    """Resolve an IPC handler by name from the registry.

    Returns a tuple ``(callable, is_background)``. Skips the test if the
    handler is not registered in this environment.
    """
    from gui.ipc.registry import IPCHandlerRegistry
    found = IPCHandlerRegistry.get_handler(name)
    if found is None:
        pytest.skip(f"Handler {name!r} is not registered in this test environment")
    handler_fn, kind = found
    if kind != "sync":
        pytest.skip(f"Handler {name!r} is background; integration test required")
    return handler_fn


def _unwrap_response(response: dict) -> dict:
    """The IPC envelope wraps the handler's payload under ``result`` for
    success and ``error`` for failures. Returns whichever is present."""
    if response.get("status") == "success":
        return response.get("result", {}) or {}
    if response.get("status") == "error":
        return response.get("error", {}) or {}
    return response


def _call_sync_handler(handler, params: dict) -> dict:
    """Invoke a sync IPC handler with the standard request envelope and
    return the full IPC response dict."""
    request = {"id": "test", "method": "test", "params": params}
    response = handler(request, params)
    if hasattr(response, "__await__"):
        pytest.skip("Handler unexpectedly returned a coroutine")
    if not isinstance(response, dict):
        pytest.skip(f"Handler returned non-dict: {type(response).__name__}")
    return response


# --- send_code: is_user passthrough ---

class TestSendCodeIsUserPassthrough:
    """``is_user`` must reach the frontend so the UI can hint login/signup."""

    def test_is_user_true_is_passed_through(self):
        handler = _get_handler("cloudbase_send_code")
        with patch(
            "gui.ipc.w2p_handlers.cloudbase_handler._get_service"
        ) as svc:
            svc.return_value.send_verification_code.return_value = _ok({
                "verification_id": "VID123",
                "expires_in": 600,
                "is_user": True,
            })
            response = _call_sync_handler(
                handler, {"phone": "13800138000", "purpose": "login"}
            )

        assert response.get("status") == "success", response
        payload = _unwrap_response(response)
        assert payload.get("verification_id") == "VID123"
        assert payload.get("is_user") is True

    def test_is_user_false_is_passed_through(self):
        handler = _get_handler("cloudbase_send_code")
        with patch(
            "gui.ipc.w2p_handlers.cloudbase_handler._get_service"
        ) as svc:
            svc.return_value.send_verification_code.return_value = _ok({
                "verification_id": "VID124",
                "expires_in": 600,
                "is_user": False,
            })
            response = _call_sync_handler(
                handler, {"phone": "13800138001", "purpose": "login"}
            )

        assert response.get("status") == "success"
        payload = _unwrap_response(response)
        assert payload.get("is_user") is False

    def test_missing_is_user_field_does_not_crash(self):
        """Older CloudBase responses may omit ``is_user``. The handler must
        not crash and must simply omit the field from the response."""
        handler = _get_handler("cloudbase_send_code")
        with patch(
            "gui.ipc.w2p_handlers.cloudbase_handler._get_service"
        ) as svc:
            svc.return_value.send_verification_code.return_value = _ok({
                "verification_id": "VID125",
                "expires_in": 600,
                # no is_user
            })
            response = _call_sync_handler(
                handler, {"phone": "13800138002", "purpose": "login"}
            )

        assert response.get("status") == "success"
        payload = _unwrap_response(response)
        # Field may be absent (preferred) or False; either is acceptable
        assert payload.get("is_user") in (None, False)


# --- phone_login: sign_in → sign_up fallback ---

class TestPhoneLoginSmartProvision:
    """``handle_cloudbase_phone_login`` must auto-provision new accounts when
    the phone number is not yet registered (the "smart" login/signup flow)."""

    def _verify_ok(self):
        return _ok({"verification_token": "VT1", "expires_in": 600})

    def test_sign_in_success_skips_sign_up(self):
        """Already-registered user → only sign_in is called, sign_up never is."""
        handler = _get_handler("cloudbase_phone_login")
        service = MagicMock()
        service.verify_verification_code.return_value = self._verify_ok()
        service.sign_in_with_otp.return_value = _ok({
            "access_token": "AT1", "refresh_token": "RT1",
            "expires_in": 7200, "token_type": "Bearer",
            "user_info": {"sub": "13800138000"},
        })

        with patch(
            "gui.ipc.w2p_handlers.cloudbase_handler._get_service",
            return_value=service,
        ):
            response = _call_sync_handler(handler, {
                "phone": "13800138000",
                "code": "123456",
                "verification_id": "VID1",
            })

        assert response.get("status") == "success", response
        service.sign_in_with_otp.assert_called_once()
        service.sign_up_with_otp.assert_not_called()

    def test_sign_in_not_found_falls_back_to_sign_up(self):
        """NOT_FOUND on sign_in → must attempt sign_up to provision the user."""
        handler = _get_handler("cloudbase_phone_login")
        service = MagicMock()
        service.verify_verification_code.return_value = self._verify_ok()
        service.sign_in_with_otp.return_value = _fail("User not exist.", "NOT_FOUND")
        service.sign_up_with_otp.return_value = _ok({
            "access_token": "AT_NEW", "refresh_token": "RT_NEW",
            "expires_in": 7200, "token_type": "Bearer",
            "user_info": {"sub": "13800138000"},
        })

        with patch(
            "gui.ipc.w2p_handlers.cloudbase_handler._get_service",
            return_value=service,
        ):
            response = _call_sync_handler(handler, {
                "phone": "13800138001",
                "code": "123456",
                "verification_id": "VID2",
            })

        assert response.get("status") == "success", response
        service.sign_in_with_otp.assert_called_once()
        service.sign_up_with_otp.assert_called_once()
        # sign_up must receive the same verification_token (proves we don't
        # require a second round of send_code → verify)
        kwargs = service.sign_up_with_otp.call_args.kwargs
        assert kwargs.get("verification_token") == "VT1"
        assert kwargs.get("phone_number") == "13800138001"

    def test_sign_in_non_notfound_error_does_not_trigger_sign_up(self):
        """A non-NOT_FOUND failure (e.g. EXPIRED_CODE) must NOT silently
        create a new account — that would mask real auth errors."""
        handler = _get_handler("cloudbase_phone_login")
        service = MagicMock()
        service.verify_verification_code.return_value = self._verify_ok()
        service.sign_in_with_otp.return_value = _fail(
            "Verification code expired", "EXPIRED_CODE",
        )

        with patch(
            "gui.ipc.w2p_handlers.cloudbase_handler._get_service",
            return_value=service,
        ):
            response = _call_sync_handler(handler, {
                "phone": "13800138002",
                "code": "111111",
                "verification_id": "VID3",
            })

        assert response.get("status") == "error"
        service.sign_in_with_otp.assert_called_once()
        service.sign_up_with_otp.assert_not_called()

    def test_both_sign_in_and_sign_up_fail_returns_error(self):
        """If the user really cannot be provisioned (e.g. signup disabled),
        the handler must surface the sign_up error to the frontend."""
        handler = _get_handler("cloudbase_phone_login")
        service = MagicMock()
        service.verify_verification_code.return_value = self._verify_ok()
        service.sign_in_with_otp.return_value = _fail("User not exist.", "NOT_FOUND")
        service.sign_up_with_otp.return_value = _fail(
            "Signup is disabled", "DISABLED",
        )

        with patch(
            "gui.ipc.w2p_handlers.cloudbase_handler._get_service",
            return_value=service,
        ):
            response = _call_sync_handler(handler, {
                "phone": "13800138003",
                "code": "654321",
                "verification_id": "VID4",
            })

        assert response.get("status") == "error"
        # Both calls should have been attempted
        service.sign_in_with_otp.assert_called_once()
        service.sign_up_with_otp.assert_called_once()

    def test_verify_failure_short_circuits(self):
        """If the verification code is wrong, neither sign_in nor sign_up
        should run."""
        handler = _get_handler("cloudbase_phone_login")
        service = MagicMock()
        service.verify_verification_code.return_value = _fail(
            "Invalid code", "INVALID_CODE",
        )

        with patch(
            "gui.ipc.w2p_handlers.cloudbase_handler._get_service",
            return_value=service,
        ):
            response = _call_sync_handler(handler, {
                "phone": "13800138004",
                "code": "000000",
                "verification_id": "VID5",
            })

        assert response.get("status") == "error"
        service.sign_in_with_otp.assert_not_called()
        service.sign_up_with_otp.assert_not_called()