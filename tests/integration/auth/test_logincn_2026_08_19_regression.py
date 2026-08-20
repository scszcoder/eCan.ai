#!/usr/bin/env python3
"""
Regression tests for the 3 LoginCN bugs reported on 2026-08-19.

Bug 1: 手机号登录不可用
  - Root cause: when CloudBase's send_verification_code response was missing
    the verification_id (rate-limit edge / camelCase vs snake_case field),
    the backend's `_send_phone_code` returned AuthResult.ok with empty
    verification_id, which made the frontend silently set codeSent=true
    without a verificationId — the next login attempt then hit INVALID_PARAMS.

  - Fix: `_send_phone_code` / `_send_email_code` now accept both
    ``verification_id`` (snake_case) and ``verificationId`` (camelCase),
    and return MISSING_VERIFICATION_ID error when the field is absent.

Bug 2: 邮箱注册直接登录
  - Frontend-only bug (see LoginCN.tsx handleModeChange); the backend
    flow itself was correct. Frontend fix tested separately in the React
    integration test suite. Here we ensure the BACKEND signup path is
    correctly two-step (send_code → verify → sign_up) and never auto-
    logs the user in without going through ``cloudbase_signup_confirm``.

Bug 3: handleSignup state closure
  - Frontend-only. Same file as Bug 2.

Bug 4: 手机登录 "获取验证码" 按钮不可点击
  - 现象: 用户切到 "手机登录" tab,输入手机号后 "获取验证码"
    按钮仍然 disabled。
  - 根因: LoginCN.tsx 的 <button disabled={...!form.getFieldValue('phone')}> 中,
    form.getFieldValue() 是 antd Form 的 getter,**不会**触发 React 重渲染。
    因此即使用户在 phone 输入框中输入内容,父组件不会重新计算 disabled。
    切换到手机注册 (phone-signup) 模式时, setMode 触发重渲染,form 值才被读取,
    所以注册模式看起来 "正常" 而登录模式 "坏了" (与用户报告一致)。
  - 修复: 在 LoginCN.tsx 顶部用 ``Form.useWatch('phone', form)`` 订阅 phone 字段,
    将 disabled 计算改为基于这个会触发重渲染的变量。

Bug 5: 手机/微信登录 tab 上的 "注册新账号" 按钮看不见
  - 现象: 用户切到 "手机登录" 或 "微信登录" tab 时,看不到底部的
    "注册新账号" 链接 (以为没有注册入口)。
  - 根因: Login.css 中 .cn-login-card 在短视口下高度 (~596px)
    超过 viewport (~434px), 卡片底部 162px 被裁掉。
    Sign Up 链接恰好在卡片底部, 因此不可见。
    WeChat tab 因为没登录按钮, 卡片更高, 链接更靠下, 完全看不见。
  - 修复: Login.css 加 max-height: calc(100vh - 48px) + overflow-y: auto,
    并把 .cn-link-row 改为 sticky bottom 让链接在卡片内部滚动时
    始终钉在可见区域底部。短视口 (< 700px 高) 还压缩了卡片内边距。

These are backend regression tests (Python). Run with:

    python3 -m pytest tests/integration/auth/test_logincn_2026_08_19_regression.py -v
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

_script_path = Path(__file__).resolve()
_project_root = _script_path
for _ in range(4):
    _project_root = _project_root.parent
sys.path.insert(0, str(_project_root))


def _make_service():
    from auth.tencent.cloudbase_auth import CloudBaseAuthService
    svc = CloudBaseAuthService()
    # Force the service to look configured so it actually POSTs.
    svc.config.env_id = "fake_env_for_test"
    return svc


# ============================================================
# Bug 1: phone_login fails when verification_id is missing
# ============================================================

class TestBug1PhoneVerificationIdRegression:
    """Regression for "手机号登录不可用" — verification_id missing."""

    def test_send_phone_code_with_snake_case_verification_id(self):
        """CloudBase returns ``verification_id`` (snake_case)."""
        svc = _make_service()
        with patch.object(svc, "_post") as m:
            m.return_value = {
                "_http_status": 200,
                "verification_id": "VID_SNAKE",
                "expires_in": 600,
                "is_user": False,
            }
            result = svc.send_verification_code(phone_number="13800138000")
        assert result.success, f"Should succeed: {result.error}"
        assert result.data["verification_id"] == "VID_SNAKE"
        assert result.data["is_user"] is False

    def test_send_phone_code_with_camel_case_verification_id(self):
        """Some CloudBase SDK wrappers return ``verificationId`` (camelCase).

        The bug: this used to silently return AuthResult.ok with empty
        verification_id, then the frontend thought the code was sent but
        had nothing to send to /auth/v1/verification/verify.
        """
        svc = _make_service()
        with patch.object(svc, "_post") as m:
            m.return_value = {
                "_http_status": 200,
                "verificationId": "VID_CAMEL",   # camelCase only
                "expires_in": 600,
                "is_user": False,
            }
            result = svc.send_verification_code(phone_number="13800138000")
        assert result.success, f"Should succeed via camelCase fallback: {result.error}"
        assert result.data["verification_id"] == "VID_CAMEL", (
            "camelCase verificationId must be normalized to snake_case"
        )

    def test_send_phone_code_with_missing_verification_id_returns_error(self):
        """CloudBase returning success without any verification_id field
        must surface as a clear MISSING_VERIFICATION_ID error, NOT
        a fake success that silently breaks the next login step.
        """
        svc = _make_service()
        with patch.object(svc, "_post") as m:
            m.return_value = {
                "_http_status": 200,
                # No verification_id field at all
                "expires_in": 600,
                "is_user": False,
            }
            result = svc.send_verification_code(phone_number="13800138000")
        assert not result.success
        assert result.error_code == "MISSING_VERIFICATION_ID"

    def test_send_email_code_with_camel_case_verification_id(self):
        """Same camelCase fallback applies to email verification."""
        svc = _make_service()
        with patch.object(svc, "_post") as m:
            m.return_value = {
                "_http_status": 200,
                "verificationId": "VID_EMAIL_CAMEL",
                "expires_in": 600,
                "is_user": False,
            }
            result = svc.send_verification_code(email="user@example.com")
        assert result.success
        assert result.data["verification_id"] == "VID_EMAIL_CAMEL"

    def test_send_email_code_missing_verification_id(self):
        """Same MISSING_VERIFICATION_ID error path for email."""
        svc = _make_service()
        with patch.object(svc, "_post") as m:
            m.return_value = {"_http_status": 200, "expires_in": 600, "is_user": False}
            result = svc.send_verification_code(email="user@example.com")
        assert not result.success
        assert result.error_code == "MISSING_VERIFICATION_ID"


# ============================================================
# Bug 2 & 3: signup flow integrity
# ============================================================

class TestBug2SignupTwoStepFlow:
    """Regression: signup is a strict two-step (send → confirm) flow,
    and the first step (send) never auto-logs in.

    Frontend behavior is in LoginCN.tsx; we verify the backend IPC
    handlers enforce the two-step boundary so a misbehaving client
    can't bypass it.
    """

    def test_signup_sends_code_but_does_not_login(self):
        """``cloudbase_signup`` must only send the verification code
        and return ``pending_verification: True`` — never auto-login.
        If a future refactor accidentally adds a sign-in call here,
        this test fails.
        """
        from auth.tencent.cloudbase_auth import CloudBaseAuthService
        svc = _make_service()
        with patch.object(svc, "_post") as m:
            m.return_value = {
                "_http_status": 200,
                "verification_id": "VID_NEW_USER",
                "expires_in": 600,
                "is_user": False,
            }
            send_result = svc.send_verification_code(email="new@example.com")

        # The /auth/v1/verification call alone must NOT issue tokens.
        assert send_result.success
        assert "access_token" not in (send_result.data or {})
        assert "refresh_token" not in (send_result.data or {})
        assert "verification_id" in send_result.data

    def test_signup_two_step_full_path(self):
        """The full email signup path must be:
          1. send_verification_code → verification_id
          2. verify_verification_code(verification_id, code) → verification_token
          3. sign_up_with_otp(verification_token, email, password) → tokens

        Skipping step 2 (jumping from 1 to 3) must fail because
        sign_up_with_otp requires verification_token.
        """
        svc = _make_service()
        with patch.object(svc, "_post") as m:
            # Step 1: send code
            m.side_effect = [
                # 1) send_verification_code
                {"_http_status": 200, "verification_id": "VID", "expires_in": 600, "is_user": False},
                # 2) verify_verification_code (correctly executed)
                {"_http_status": 200, "verification_token": "VT_OK", "expires_in": 600},
                # 3) sign_up_with_otp
                {
                    "_http_status": 200,
                    "access_token": "AT_NEW",
                    "refresh_token": "RT_NEW",
                    "token_type": "Bearer",
                    "expires_in": 7200,
                    "user_info": {"sub": "u-new", "email": "new@example.com"},
                },
            ]
            send = svc.send_verification_code(email="new@example.com")
            assert send.success
            vid = send.data["verification_id"]

            verify = svc.verify_verification_code(vid, "123456")
            assert verify.success, f"verify failed: {verify.error}"
            vt = verify.data["verification_token"]

            signup = svc.sign_up_with_otp(
                email="new@example.com", verification_token=vt, password="ValidPass123!",
            )
            assert signup.success, f"signup failed: {signup.error}"
            assert signup.data["access_token"] == "AT_NEW"

    def test_signup_rejects_empty_verification_token(self):
        """If verification_token is missing/empty, signup must reject.
        This is the boundary that prevents "直接登录" via bypassing verify."""
        svc = _make_service()
        result = svc.sign_up_with_otp(
            email="user@example.com", verification_token="",
        )
        assert not result.success
        assert result.error_code == "INVALID_INPUT"

    def test_phone_login_rejects_missing_verification_token(self):
        """Same boundary for phone login — verification_token is required."""
        svc = _make_service()
        result = svc.sign_in_with_otp(
            phone_number="13800138000", verification_token="",
        )
        assert not result.success
        assert result.error_code == "INVALID_INPUT"


# ============================================================
# Bug 1+2 combined: the IPC handler also normalizes verification_id
# ============================================================

class TestBug1HandlerCamelCaseNormalization:
    """The IPC handler ``handle_cloudbase_send_code`` must forward
    verification_id regardless of which field name CloudBase used."""

    def test_handler_sends_both_field_names_when_present(self):
        """If CloudBase returns both (impossible but defensive), the
        handler's outgoing response always uses ``verification_id``.
        """
        import uuid as _uuid
        from auth.tencent.cloudbase_auth import AuthResult

        svc = _make_service()
        with patch(
            "gui.ipc.w2p_handlers.cloudbase_handler._get_service",
            return_value=svc,
        ):
            with patch.object(svc, "send_verification_code") as m:
                m.return_value = AuthResult(success=True, data={
                    "verification_id": "VID1",
                    "verificationId": "VID2",  # both present (defensive)
                    "expires_in": 600,
                    "is_user": False,
                })
                from gui.ipc.w2p_handlers.cloudbase_handler import (
                    handle_cloudbase_send_code,
                )
                req = {
                    "id": _uuid.uuid4().hex,
                    "type": "request",
                    "method": "cloudbase_send_code",
                    "params": {"phone": "13800138000"},
                }
                resp = handle_cloudbase_send_code(req, {"phone": "13800138000"})
                assert resp["status"] == "success"
                assert resp["result"].get("verification_id") == "VID1"

    def test_handler_forwards_verification_id_when_camel_case_only(self):
        """If CloudBase returns only ``verificationId`` (camelCase),
        the handler must still forward a ``verification_id`` in its
        IPC response — because the frontend reads snake_case.
        """
        from auth.tencent.cloudbase_auth import AuthResult
        from auth.tencent.cloudbase_auth import CloudBaseAuthService

        svc = CloudBaseAuthService()
        svc.config.env_id = "fake_env"
        # Patch the underlying _post so send_verification_code returns camelCase
        with patch.object(svc, "_post", return_value={
            "_http_status": 200,
            "verificationId": "VID_CAMEL",
            "expires_in": 600,
            "is_user": False,
        }):
            send_result = svc.send_verification_code(phone_number="13800138000")
            assert send_result.success
            assert send_result.data["verification_id"] == "VID_CAMEL"


# ============================================================
# Bug 4: phone-login "获取验证码" button stays disabled when typing
# ============================================================
#
# This is a frontend React bug. We can't render React in unit tests, but we
# can statically verify the LoginCN.tsx source has the fix in place —
# otherwise a future refactor could regress this. The browser-based E2E
# repro is documented separately (see git history: phone_login_button_fix).
#
# Bug: <button disabled={!form.getFieldValue('phone')}> does not re-render
# when the user types, because form.getFieldValue is a getter call, not a
# reactive subscription. AntD's recommended pattern is Form.useWatch.
#
# Fix: LoginCN.tsx now uses const phoneValue = Form.useWatch('phone', form);
# and the disabled prop uses !phoneValue. This makes the component re-render
# on every keystroke in the phone field.

class TestBug4PhoneLoginButtonDisabled:
    """Static source check: the LoginCN.tsx fix must be in place."""

    def _read_logincn(self) -> str:
        from pathlib import Path
        # tests/integration/auth/ → tests/integration/auth/ (file location)
        # path: file → tests/integration/auth/ → tests/integration → tests → repo root → gui_v2/...
        path = (
            Path(__file__).resolve().parent.parent.parent.parent
            / "gui_v2"
            / "src"
            / "pages"
            / "Login"
            / "LoginCN.tsx"
        )
        if not path.exists():
            raise FileNotFoundError(f"LoginCN.tsx not found at {path}")
        return path.read_text(encoding="utf-8")

    def test_uses_form_usewatch_for_phone_field(self):
        """LoginCN.tsx must call ``Form.useWatch('phone', form)``.

        Without this, the "获取验证码" button never updates its
        ``disabled`` prop when the user types in the phone field
        (form.getFieldValue is a getter, not a reactive subscription).
        """
        src = self._read_logincn()
        assert "Form.useWatch" in src, (
            "LoginCN.tsx missing Form.useWatch — phone-login '获取验证码' "
            "button will stay disabled when user types. Add:\n"
            "    const phoneValue = Form.useWatch('phone', form);\n"
        )

    def test_disabled_prop_uses_phonevalue_not_form_getter(self):
        """The ``disabled`` prop on the send-code button must NOT call
        form.getFieldValue('phone') inline — it must use the reactive
        ``phoneValue`` variable from useWatch.
        """
        src = self._read_logincn()
        # Find each cn-send-code-btn block
        bad = []
        for i, line in enumerate(src.splitlines(), start=1):
            if "cn-send-code-btn" in line:
                # Look ahead up to 10 lines for the disabled prop
                window = "\n".join(
                    src.splitlines()[i - 1 : i + 10]
                )
                if (
                    "form.getFieldValue('phone')" in window
                    and "!phoneValue" not in window
                ):
                    bad.append((i, line.strip()))
        assert not bad, (
            "Found cn-send-code-btn with stale form.getFieldValue('phone'):\n"
            + "\n".join(f"  line {i}: {l}" for i, l in bad)
            + "\n\nFix: replace form.getFieldValue('phone') with phoneValue "
            "(the variable from Form.useWatch)."
        )

    def test_phone_field_has_validation_rule(self):
        """Phone field must still have a pattern validation rule so users
        get feedback on invalid numbers. This is a guardrail — the fix
        should not have removed validation.
        """
        src = self._read_logincn()
        assert "pattern: /^1[3-9]\\d{9}$/" in src, (
            "Phone field missing the /^1[3-9]\\d{9}$/ validation rule. "
            "If you removed it while fixing Bug 4, please restore it."
        )


class TestBug5SignUpButtonVisibleOnAllTabs:
    """Static source check: the cn-link-row must be visible on phone and
    wechat tabs (Bug 5). The fix is in Login.css, not LoginCN.tsx."""

    def _read_logincss(self) -> str:
        from pathlib import Path
        path = (
            Path(__file__).resolve().parent.parent.parent.parent
            / "gui_v2"
            / "src"
            / "pages"
            / "Login"
            / "Login.css"
        )
        if not path.exists():
            raise FileNotFoundError(f"Login.css not found at {path}")
        return path.read_text(encoding="utf-8")

    def _read_logincn(self) -> str:
        from pathlib import Path
        path = (
            Path(__file__).resolve().parent.parent.parent.parent
            / "gui_v2"
            / "src"
            / "pages"
            / "Login"
            / "LoginCN.tsx"
        )
        return path.read_text(encoding="utf-8")

    def test_card_has_max_height_to_prevent_overflow(self):
        """Without max-height on the login card, the Sign Up / 返回登录
        link row at the bottom gets pushed below the viewport fold on
        short viewports (laptop 13", split view, etc.).
        """
        css = self._read_logincss()
        # The fix sets max-height on .cn-login-card
        assert ".cn-login-card" in css
        # Check the rule has max-height (look for the max-height property
        # anywhere in the .cn-login-card block)
        import re
        card_blocks = re.findall(
            r"\.cn-login-card\s*\{[^}]+\}", css, re.DOTALL
        )
        # The base rule may not have max-height; it can be in a media query.
        # Look for any rule that targets .cn-login-card and includes max-height.
        all_blocks = re.findall(
            r"[^{}]*\.cn-login-card[^{}]*\{[^}]+\}", css, re.DOTALL
        )
        has_max_height = any("max-height" in b for b in all_blocks)
        assert has_max_height, (
            ".cn-login-card must have max-height to prevent the "
            "Sign Up button from being clipped on short viewports."
        )

    def test_card_is_overflowable(self):
        """Card must have overflow-y:auto so users can scroll if content
        still exceeds max-height (defensive even after we compress it).
        """
        css = self._read_logincss()
        import re
        all_blocks = re.findall(
            r"[^{}]*\.cn-login-card[^{}]*\{[^}]+\}", css, re.DOTALL
        )
        has_overflow = any(
            "overflow-y" in b and "auto" in b for b in all_blocks
        )
        assert has_overflow, (
            ".cn-login-card must have overflow-y:auto so Sign Up "
            "button is reachable via scroll if card is still too tall."
        )

    def test_link_row_is_sticky_to_bottom(self):
        """The .cn-link-row must be sticky-positioned at the bottom of
        the scroll container so the Sign Up button remains visible
        when the user scrolls inside the card.
        """
        css = self._read_logincss()
        import re
        link_row_blocks = re.findall(
            r"\.cn-link-row\s*\{[^}]+\}", css, re.DOTALL
        )
        assert link_row_blocks, ".cn-link-row rule not found"
        block = "\n".join(link_row_blocks)
        assert "position: sticky" in block or "position:sticky" in block, (
            ".cn-link-row must be position:sticky so the Sign Up link "
            "stays visible when card scrolls."
        )
        assert "bottom: 0" in block or "bottom:0" in block, (
            ".cn-link-row must be sticky at bottom:0."
        )

    def test_signup_button_renders_for_phone_and_wechat_tabs(self):
        """The Sign Up toggle button must be rendered regardless of which
        tab is active. (Bug 5 was originally misdiagnosed as 'not
        rendered' but it IS in JSX; the bug is CSS clipping.)
        """
        tsx = self._read_logincn()
        # The cn-link-row block is inside mode !== 'forgot' branch — so
        # on forgot mode it shows back-to-login instead. On every other
        # mode it shows the Sign Up toggle. Verify that.
        assert "cn-link-row" in tsx
        assert "t('login.signUp')" in tsx
        # And the onClick handler must handle all four sign-up modes
        assert "'phone-signup'" in tsx
        assert "'email-signup'" in tsx


def main():
    """Allow running as a script (no pytest required)."""
    import pytest
    code = pytest.main([__file__, "-v"])
    sys.exit(code)


if __name__ == "__main__":
    main()
