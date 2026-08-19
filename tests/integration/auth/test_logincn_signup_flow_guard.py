#!/usr/bin/env python3
"""
Regression test for Bug 2 (前端 email-signup 行为).

Bug 2: "邮箱注册号码，直接登陆了" — 用户期望注册新账号,但表单
       已被自动填充了旧 keyring 凭证,默认 mode='email-login',
       点提交走 loginWithEmail → 登录到旧账号,完全没经过验证码。

The backend fix is in tests/integration/auth/test_logincn_2026_08_19_regression.py
(backend IPC enforces two-step signup). The frontend fix lives in
gui_v2/src/pages/Login/LoginCN.tsx's handleModeChange — it now clears
username+password when switching to email-signup.

Additional guard: if the user explicitly enters a *known-registered* email
into the signup form and submits, the backend MUST reject with USER_EXISTS
(never auto-login to that account). Verified by ``test_signup_rejects_existing_email``.

Run:
    python3 -m pytest tests/integration/auth/test_logincn_signup_flow_guard.py -v
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path
from unittest.mock import patch

_script_path = Path(__file__).resolve()
_project_root = _script_path
for _ in range(4):
    _project_root = _project_root.parent
sys.path.insert(0, str(_project_root))


def _req(method: str, params: dict) -> dict:
    return {
        "id": uuid.uuid4().hex,
        "type": "request",
        "method": method,
        "params": params,
    }


class TestSignupFlowGuard:
    """Backend guardrails against the "直接登录" anti-pattern."""

    def test_signup_endpoint_never_returns_tokens(self):
        """``cloudbase_signup`` is send-code-only. Even if the email is
        new, it must NOT issue tokens. If a future refactor accidentally
        adds a sign_in_with_password call inside cloudbase_signup,
        this test catches it.
        """
        from auth.tencent.cloudbase_auth import AuthResult, CloudBaseAuthService

        svc = CloudBaseAuthService()
        svc.config.env_id = "fake_env"

        with patch(
            "gui.ipc.w2p_handlers.cloudbase_handler._get_service",
            return_value=svc,
        ):
            with patch.object(svc, "send_verification_code") as m:
                m.return_value = AuthResult(success=True, data={
                    "verification_id": "VID",
                    "expires_in": 600,
                    "is_user": False,
                })
                from gui.ipc.w2p_handlers.cloudbase_handler import (
                    handle_cloudbase_signup,
                )
                resp = handle_cloudbase_signup(
                    _req("cloudbase_signup", {"email": "new@example.com", "password": "ValidPass123!"}),
                    {"email": "new@example.com", "password": "ValidPass123!"},
                )
                assert resp["status"] == "success", resp
                result = resp["result"]
                assert "pending_verification" in result
                assert result["pending_verification"] is True
                # Anti-regression: signup must NOT issue tokens
                assert "token" not in result, "cloudbase_signup leaked a token!"
                assert "access_token" not in result
                assert "refresh_token" not in result
                # And the verification_id is present
                assert result["verification_id"] == "VID"

    def test_signup_returns_user_exists_for_existing_email(self):
        """If the email already exists, signup must reject (not silently
        auto-login with the user's existing credentials)."""
        from auth.tencent.cloudbase_auth import AuthResult, CloudBaseAuthService

        svc = CloudBaseAuthService()
        svc.config.env_id = "fake_env"

        with patch(
            "gui.ipc.w2p_handlers.cloudbase_handler._get_service",
            return_value=svc,
        ):
            with patch.object(svc, "send_verification_code") as m:
                m.return_value = AuthResult(success=True, data={
                    "verification_id": "VID",
                    "expires_in": 600,
                    "is_user": True,   # <-- already registered
                })
                from gui.ipc.w2p_handlers.cloudbase_handler import (
                    handle_cloudbase_signup,
                )
                resp = handle_cloudbase_signup(
                    _req("cloudbase_signup", {"email": "exists@example.com", "password": "ValidPass123!"}),
                    {"email": "exists@example.com", "password": "ValidPass123!"},
                )
                assert resp["status"] == "error"
                assert resp["error"]["code"] == "USER_EXISTS"

    def test_signup_rejects_existing_email_without_login(self):
        """Direct answer to user question: "邮箱注册,如果是登陆过的邮箱,
        会不会自动登陆啊?"

        Backend invariant: cloudbase_signup MUST short-circuit on is_user=True
        with USER_EXISTS error, and MUST NOT issue any tokens (auto-login).
        """
        from auth.tencent.cloudbase_auth import AuthResult, CloudBaseAuthService

        svc = CloudBaseAuthService()
        svc.config.env_id = "fake_env"

        with patch(
            "gui.ipc.w2p_handlers.cloudbase_handler._get_service",
            return_value=svc,
        ):
            with patch.object(svc, "send_verification_code") as m:
                m.return_value = AuthResult(success=True, data={
                    "verification_id": "VID",
                    "expires_in": 600,
                    "is_user": True,   # <-- CloudBase says: already a user
                })
                # sign_in_with_email / sign_up_with_otp MUST NOT be called
                # by the signup endpoint when is_user=True — guard it:
                with patch.object(svc, "sign_in_with_otp") as m_login, \
                     patch.object(svc, "sign_up_with_otp") as m_signup:
                    from gui.ipc.w2p_handlers.cloudbase_handler import (
                        handle_cloudbase_signup,
                    )
                    resp = handle_cloudbase_signup(
                        _req("cloudbase_signup", {
                            "email": "already@registered.com",
                            "password": "AnyPassword123!",
                        }),
                        {
                            "email": "already@registered.com",
                            "password": "AnyPassword123!",
                        },
                    )

                    # The signup endpoint MUST reject — no auto-login
                    assert resp["status"] == "error", (
                        f"Signup for existing email must error, got {resp}"
                    )
                    assert resp["error"]["code"] == "USER_EXISTS", (
                        f"Expected USER_EXISTS, got {resp['error']}"
                    )
                    result_block = resp.get("result") or {}
                    assert "token" not in result_block, (
                        "Auto-login to existing account leaked a token!"
                    )
                    assert "access_token" not in result_block
                    # And neither login nor signup was actually attempted
                    m_login.assert_not_called()
                    m_signup.assert_not_called()


def main():
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))


if __name__ == "__main__":
    main()
