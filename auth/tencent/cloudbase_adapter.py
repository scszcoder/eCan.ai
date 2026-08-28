"""
CloudBase ↔ Cognito Service Adapter
===================================

Goal: make ``AuthManager`` work identically for CN (CloudBase Web v3) and
Intl (AWS Cognito) builds, by exposing the *same* method names and the
*same* return-dict shape that ``CognitoService`` provides.

Every method returns::

    {"success": bool, "data": <cognito-shape>, "error": <code-or-message>}

Inside ``AuthManager``, ``self.cognito_service`` is replaced with an
instance of this adapter on CN builds (see ``AuthManager.__init__``).
The refresh loop, ``_fetch_user_profile``, ``try_restore_session`` and
the high-level ``login``/``sign_up``/``forgot_password``/``logout``
methods all keep working unchanged — they only ever talked to
``self.cognito_service`` and read ``self.tokens``.

CloudBase vs Cognito token key mapping
--------------------------------------
CloudBase returns::

    {token_type, access_token, refresh_token, expires_in, user_info: {...}}

Cognito ``AuthenticationResult`` returns::

    {AccessToken, IdToken, RefreshToken, ExpiresIn, TokenType}

We normalize CloudBase → Cognito casing so the existing refresh loop,
``_get_best_id_token`` / ``_get_best_access_token`` and
``try_restore_session`` all work without modification.

Mapping rules applied in ``_normalize_tokens``::

    access_token  → AccessToken
    refresh_token → RefreshToken  (kept unchanged if already present)
    expires_in    → ExpiresIn
    token_type    → TokenType  ("Bearer")
    user_info     → dropped here; ``user_profile`` is rebuilt separately
                    by ``AuthManager._fetch_user_profile``.

Notes
-----
- This adapter does NOT replace ``CloudBaseAuthService``. It composes it
  and only handles shape translation + a few utility methods.
- ``verify_token`` is intentionally a no-op (returns ``{"success":
  False, "error": "NOT_SUPPORTED_ON_CN"}``) — CN's token verification
  uses ``_decode_jwt_payload_unsafe`` instead (see
  ``AuthManager._fetch_user_profile`` CN branch).
"""

from __future__ import annotations

import os
import time
import uuid
from typing import Any, Dict, Optional

from auth.tencent.cloudbase_auth import (
    AuthResult,
    CloudBaseAuthService,
    CloudBaseUserInfo,
)
from auth.tencent.cloudbase_config import CloudBaseConfig
from utils.logger_helper import logger_helper as logger


# ============================================================
# Result-shape helpers
# ============================================================

def _ok(data: Dict[str, Any]) -> Dict[str, Any]:
    return {"success": True, "data": data, "error": None}


def _fail(error: str, code: Optional[str] = None) -> Dict[str, Any]:
    return {"success": False, "data": None, "error": code or error, "error_code": code}


def _normalize_tokens(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Translate CloudBase token payload into Cognito's AuthenticationResult shape.

    Output keys: ``AccessToken``, ``IdToken`` (None — CloudBase doesn't
    issue one), ``RefreshToken``, ``ExpiresIn``, ``TokenType``.
    """
    access = raw.get("access_token")
    refresh = raw.get("refresh_token") or raw.get("RefreshToken")
    expires_in = raw.get("expires_in", 7200)
    token_type = raw.get("token_type", "Bearer")

    out: Dict[str, Any] = {
        "AccessToken": access,
        "IdToken": None,  # CloudBase Web v3 doesn't issue an IdToken
        "RefreshToken": refresh,
        "ExpiresIn": int(expires_in) if expires_in else 7200,
        "TokenType": token_type,
    }
    # Keep the CloudBase user_info alongside for CN-specific consumers
    # (e.g. AuthManager._fetch_user_profile CN branch). It's ignored by
    # the refresh loop.
    if "user_info" in raw:
        out["UserInfo"] = raw["user_info"]
    return out


def _authresult_to_dict(result: AuthResult) -> Dict[str, Any]:
    """Translate ``CloudBaseAuthService.AuthResult`` into Cognito-shape dict."""
    if result.success and isinstance(result.data, dict):
        return _ok(_normalize_tokens(result.data))
    return _fail(result.error or "UNKNOWN_ERROR", result.error_code)


# ============================================================
# Adapter
# ============================================================

class CloudBaseAuthAdapter:
    """``CognitoService``-shaped facade over ``CloudBaseAuthService``.

    Used as ``AuthManager.cognito_service`` on CN builds. Every method
    returns a dict shaped like Cognito's boto3 response wrapper:
    ``{"success": bool, "data": dict, "error": str|None}``.
    """

    def __init__(self, service: Optional[CloudBaseAuthService] = None):
        self._service = service or CloudBaseAuthService()
        self.config = self._service.config
        # Parity with CognitoService — AuthManager reads a couple of
        # attributes (cognito_client, jwks) defensively. CloudBase has
        # neither; expose dummies so attribute access doesn't AttributeError.
        self.cognito_client = None
        self.jwks = None

    # --------------------------------------------------------
    # Cognito parity — high-level methods
    # --------------------------------------------------------

    def login(self, username: str, password: str) -> Dict[str, Any]:
        """Username + password login.

        NOTE: CloudBase identifies users by ``email`` (or phone). For
        username-style identifiers (the ones created by Tencent Cloud
        console or sign_up), CloudBase accepts them as ``username``.
        Caller passes whatever the user typed.
        """
        result = self._service.sign_in_with_password(username, password)
        return _authresult_to_dict(result)

    def sign_up(self, username: str, password: str) -> Dict[str, Any]:
        """Direct username+password signup.

        CloudBase Web v3 policy forbids this client-side — signup MUST
        include a ``verification_token`` (email/phone OTP). Caller is
        responsible for first calling ``send_verification_code`` →
        ``verify_verification_code`` and then re-driving through
        ``AuthManager.sign_up_with_otp``. Here we raise so the caller
        never silently gets a confusing 400.
        """
        return _fail(
            "CN signup requires email/phone verification code. "
            "Use AuthManager.sign_up_with_otp or the "
            "cloudbase_signup/cloudbase_signup_confirm IPC endpoints.",
            "SIGNUP_REQUIRES_OTP",
        )

    def confirm_sign_up(self, username: str, confirmation_code: str) -> Dict[str, Any]:
        """Cognito parity — CloudBase uses /auth/v1/verification/verify."""
        # CloudBase's verify endpoint returns a verification_token, not
        # direct signup confirmation. Higher-level signup completion
        # belongs in ``AuthManager.sign_up_with_otp``.
        return _fail(
            "CN uses sign_up_with_otp. See AuthManager.sign_up_with_otp.",
            "USE_SIGNUP_WITH_OTP",
        )

    def forgot_password(self, username: str) -> Dict[str, Any]:
        """Send a verification code to the user's phone/email.

        For CN we always go through phone since ``forgot_password`` IPC
        is invoked with a phone number (see cloudbase_handler). The
        username here may be either an email or phone — CloudBase's
        ``send_verification_code`` accepts both.
        """
        is_phone = any(c.isdigit() for c in username) and "@" not in username
        if is_phone:
            result = self._service.send_verification_code(phone_number=username)
        else:
            result = self._service.send_verification_code(email=username)
        if not result.success:
            return _fail(result.error or "SEND_FAILED", result.error_code)
        return _ok({
            "CodeDeliveryDetails": {
                "Destination": username,
                "DeliveryMedium": "SMS" if is_phone else "EMAIL",
            },
            **({"verification_id": result.data.get("verification_id")}
               if result.data else {}),
        })

    def confirm_forgot_password(
        self, username: str, confirmation_code: str, new_password: str
    ) -> Dict[str, Any]:
        """Cognito parity — three-step CN reset requires ``verification_id``.

        Without it (legacy intl IPC contract only passes code) we can't
        complete the flow. Surface a clean error so the caller can
        re-route through the CN IPC pair
        (cloudbase_forgot_password → cloudbase_reset_password).
        """
        return _fail(
            "CN password reset requires verification_id from "
            "cloudbase_forgot_password. See AuthManager.reset_password_with_otp.",
            "RESET_REQUIRES_VERIFICATION_ID",
        )

    def refresh_tokens(self, refresh_token: str) -> Dict[str, Any]:
        """Refresh access_token. Returns Cognito AuthenticationResult shape."""
        result = self._service.refresh_token(refresh_token)
        if not result.success:
            code = result.error_code or "REFRESH_FAILED"
            # Mirror Cognito's fatal-error strings so the refresh loop
            # in AuthManager._token_refresh_loop stops cleanly when the
            # refresh token is revoked/invalid.  CloudBase's HTTP layer
            # also surfaces generic 4xx codes (``HTTP_400``, ``HTTP_401``)
            # when the server can't or won't honour a refresh — those are
            # just as fatal (the server's call is the source of truth;
            # there is no point hammering it again), so map them too.
            if (
                code in ("INVALID_REFRESH_TOKEN", "INVALID_GRANT", "UNAUTHORIZED")
                or (isinstance(code, str) and code.startswith("HTTP_4"))
            ):
                code = "NotAuthorizedException"
            return _fail(result.error or code, code)
        return _ok(_normalize_tokens(result.data))

    def get_userinfo(self, access_token: str) -> Dict[str, Any]:
        """Cognito parity — fetch claims via /auth/v1/user/me."""
        result = self._service.get_current_user(access_token)
        if not result.success:
            return _fail(result.error or "USERINFO_FAILED", result.error_code)
        return _ok(result.data or {})

    def verify_token(self, token: str, token_use: str = "access") -> Dict[str, Any]:
        """No-op on CN — CloudBase JWTs are decoded unverified via
        ``_decode_jwt_payload_unsafe`` instead. The refresh loop and
        CN profile fetcher never call ``verify_token``; this only exists
        for attribute parity.
        """
        return _fail("CN uses unverified JWT decode; see _decode_jwt_payload_unsafe",
                     "NOT_SUPPORTED_ON_CN")

    def get_google_login_url(self, redirect_uri: str,
                             pkce_params: Optional[Dict[str, Any]] = None
                             ) -> Dict[str, Any]:
        """Cognito parity — only used on Intl. CN raises."""
        return _fail("Google login is not supported on CN build", "DISABLED")

    def exchange_code_for_tokens(self, code: str, redirect_uri: str,
                                 code_verifier: Optional[str] = None
                                 ) -> Dict[str, Any]:
        """Cognito parity — only used on Intl Google flow. CN raises."""
        return _fail("Google token exchange is not supported on CN build",
                     "DISABLED")

    # --------------------------------------------------------
    # CN-specific entry points (used by AuthManager.wechat_login and
    # CN signup flows). NOT part of the Cognito parity surface.
    # --------------------------------------------------------

    def sign_up_with_otp(self, *, phone_number: Optional[str] = None,
                         email: Optional[str] = None,
                         verification_token: str,
                         username: Optional[str] = None,
                         password: Optional[str] = None) -> Dict[str, Any]:
        """Sign up via email/phone OTP. Returns Cognito-shape dict on success."""
        result = self._service.sign_up_with_otp(
            phone_number=phone_number,
            email=email,
            verification_token=verification_token,
            username=username,
            password=password,
        )
        return _authresult_to_dict(result)

    def reset_password_with_otp(self, *, phone_number: Optional[str] = None,
                                email: Optional[str] = None,
                                verification_id: str,
                                verification_code: str,
                                new_password: str) -> Dict[str, Any]:
        """Reset password via email/phone OTP. Returns Cognito-shape dict."""
        result = self._service.reset_password(
            phone_number=phone_number,
            email=email,
            new_password=new_password,
            verification_id=verification_id,
            verification_code=verification_code,
        )
        if not result.success:
            return _fail(result.error or "RESET_FAILED", result.error_code)
        return _ok({})

    def get_wechat_qrcode_uri(self, *, state: Optional[str] = None,
                              redirect_uri: Optional[str] = None
                              ) -> Dict[str, Any]:
        """Resolve a WeChat Open Platform authorization URI via CloudBase."""
        result = self._service.get_wechat_qrcode_link(
            state=state, redirect_uri=redirect_uri,
        )
        if not result.success:
            return _fail(result.error or "WECHAT_URI_FAILED", result.error_code)
        return _ok(result.data or {})

    def sign_in_anonymously(self) -> Dict[str, Any]:
        """Anonymous login — parity helper, returns Cognito-shape dict."""
        result = self._service.sign_in_anonymously()
        return _authresult_to_dict(result)

    def sign_out(self, access_token: str) -> Dict[str, Any]:
        """Server-side session invalidation."""
        result = self._service.sign_out(access_token)
        if not result.success:
            return _fail(result.error or "LOGOUT_FAILED", result.error_code)
        return _ok({"message": "Logout successful"})


# ============================================================
# Module-level singleton
# ============================================================

_adapter_instance: Optional[CloudBaseAuthAdapter] = None


def get_cloudbase_adapter() -> CloudBaseAuthAdapter:
    """Get a process-wide singleton adapter instance."""
    global _adapter_instance
    if _adapter_instance is None:
        _adapter_instance = CloudBaseAuthAdapter()
    return _adapter_instance