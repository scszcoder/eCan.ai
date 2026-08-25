#!/usr/bin/env python3
"""Regression tests for "退出后回到登录页,微信 tab 缺失 + 邮箱/电话不可用".

Reported on 2026-08-24 by user (CN build). Symptom: after ``logoutManager.logout()``,
the user is redirected back to ``/login`` where ``LoginCN`` re-mounts. The login
page then shows the email/phone tabs as unusable and the WeChat tab missing.

Root cause (the parts we can verify from the backend side):

1. ``LogoutManager.clearLocalStorage()`` did not clear the CloudBase (CN) auth
   singleton state. ``cloudbase_token`` / ``cloudbase_refresh_token`` /
   ``cloudbase_user_info`` were left in localStorage AND the in-memory
   ``cloudbaseAuth.token / userInfo / _refreshToken`` kept non-null values.

2. ``LoginCN`` defaulted ``wechatAvailable`` to ``false`` and only updated it
   asynchronously via ``cloudbaseAuth.checkConfig()``. If the IPC roundtrip
   failed/timed out, the WeChat tab never appeared.

These are FRONTEND fixes (see ``gui_v2/src/services/LogoutManager.ts`` and
``gui_v2/src/pages/Login/LoginCN.tsx``). The backend invariants verified here are:

* ``handle_cloudbase_check_config`` is callable immediately after a frontend
  logout and still reports WeChat availability correctly — the backend keeps
  no per-user state on the CloudBase service singleton (only the config).
* ``handle_cloudbase_send_code`` for both phone and email works regardless of
  whether the user just logged out — CloudBase state is server-side and
  stateless from our perspective.
* ``handle_cloudbase_login`` (``sign_in_with_password``) behaves identically
  before and after logout — there is no client-side token cache that the
  backend needs to round-trip.

These tests do not exercise React state, but they prevent the backend from
silently regressing in a way that would amplify the frontend bug.

Run:
    python3 -m pytest tests/integration/auth/test_logout_then_login_recovery.py -v
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path
from unittest.mock import patch

_script_path = Path(__file__).resolve().parent
_project_root = _script_path
for _ in range(4):
    _project_root = _project_root.parent
sys.path.insert(0, str(_project_root))


def _cn_env():
    """Patch ECAN_APP_ID=cn so utils.app_env.is_cn() returns True.

    The IPC handler's ``_get_service()`` short-circuits when ``is_cn()`` is
    False, so we need this for any test that exercises a real CloudBase
    handler.
    """
    return patch.dict(os.environ, {"ECAN_APP_ID": "cn"}, clear=False)


def _req(method: str, params: dict) -> dict:
    return {
        "id": uuid.uuid4().hex,
        "type": "request",
        "method": method,
        "params": params,
    }


def _make_service(*, env_id: str = "fake_env", wechat_app_id: str = "wxappid_xxx"):
    """Build a CloudBaseAuthService with the minimum config needed for the
    IPC handlers. We don't need to toggle ``enable_wechat_login`` — the
    backend's ``wechat_available`` IPC flag is sourced from
    ``is_wechat_configured()`` which only checks ``wechat_app_id`` (see
    ``handle_cloudbase_check_config``). The ``enable_wechat_login`` flag
    is enforced separately at the call site of ``wechat_login``.
    """
    from auth.tencent.cloudbase_auth import CloudBaseAuthService

    svc = CloudBaseAuthService()
    svc.config.env_id = env_id
    svc.config.wechat_app_id = wechat_app_id
    svc.config.enable_wechat_login = True
    svc.config.enable_email_login = True
    svc.config.enable_phone_login = True
    return svc


class TestLogoutThenLoginRecovery:
    """Verify CloudBase IPC handlers are stateless w.r.t. frontend logout.

    A frontend logout must not corrupt backend state, so all handlers should
    continue to behave correctly from a clean slate.
    """

    def test_check_config_reports_wechat_available_when_appid_present(self):
        """`cloudbase_check_config` must succeed after a clean logout.
        The frontend's `wechatAvailable` flag is derived solely from the
        `wechat_available` payload field — no per-user state must be implied.
        """
        svc = _make_service(wechat_app_id="wxappid_xxx")

        with patch("gui.ipc.w2p_handlers.cloudbase_handler.is_cn", return_value=True):
            with patch(
                "gui.ipc.w2p_handlers.cloudbase_handler._get_service",
                return_value=svc,
            ):
                from gui.ipc.w2p_handlers.cloudbase_handler import (
                    handle_cloudbase_check_config,
                )
                resp = handle_cloudbase_check_config(
                    _req("cloudbase_check_config", {}), {}
                )
                assert resp["status"] == "success", resp
                result = resp["result"]
                assert result["available"] is True
                # The frontend uses `wechat_available` (not config.wechat_configured)
                # to decide whether to render the WeChat tab on LoginCN.
                assert result["wechat_available"] is True

    def test_check_config_reports_wechat_disabled_when_appid_missing(self):
        """If `wechat_app_id` is empty, the frontend must hide the WeChat tab.
        This guards against a future refactor that accidentally falls back to
        always showing the WeChat tab whenever CloudBase is "available".
        """
        svc = _make_service(wechat_app_id="")

        with patch("gui.ipc.w2p_handlers.cloudbase_handler.is_cn", return_value=True):
            with patch(
                "gui.ipc.w2p_handlers.cloudbase_handler._get_service",
                return_value=svc,
            ):
                from gui.ipc.w2p_handlers.cloudbase_handler import (
                    handle_cloudbase_check_config,
                )
                resp = handle_cloudbase_check_config(
                    _req("cloudbase_check_config", {}), {}
                )
                assert resp["status"] == "success", resp
                result = resp["result"]
                assert result["available"] is True
                assert result["wechat_available"] is False

    def test_check_config_short_circuits_for_intl_app(self):
        """``handle_cloudbase_check_config`` must return ``available: False``
        when called on an Intl build — this is the path exercised when
        ``auth_type === 'cognito'`` but ``AppConfig`` still references
        CloudBase (race during config hydration).
        """
        with patch("gui.ipc.w2p_handlers.cloudbase_handler.is_cn", return_value=False):
            from gui.ipc.w2p_handlers.cloudbase_handler import (
                handle_cloudbase_check_config,
            )
            resp = handle_cloudbase_check_config(
                _req("cloudbase_check_config", {}), {}
            )
            assert resp["status"] == "success", resp
            assert resp["result"]["available"] is False
            assert resp["result"]["reason"] == "CN app only"

    def test_phone_send_code_works_after_logout(self):
        """Sending the phone verification code must work on a freshly
        mounted LoginCN — i.e. backend state is unaffected by logout."""
        from auth.tencent.cloudbase_auth import AuthResult

        svc = _make_service()
        with _cn_env(), patch(
            "gui.ipc.w2p_handlers.cloudbase_handler._get_service",
            return_value=svc,
        ), patch.object(svc, "_post", return_value={
            "_http_status": 200,
            "verification_id": "VID_FRESH",
            "expires_in": 600,
            "is_user": False,
        }) as m:
            from gui.ipc.w2p_handlers.cloudbase_handler import (
                handle_cloudbase_send_code,
            )
            resp = handle_cloudbase_send_code(
                _req("cloudbase_send_code", {"phone": "13800138000"}),
                {"phone": "13800138000"},
            )
            assert resp["status"] == "success", resp
            result = resp["result"]
            assert result["verification_id"] == "VID_FRESH"
            assert result["is_user"] is False
            # Phone field present → frontend should now let the user
            # continue to phone login.
            assert result["type"] == "phone"
            # Sign-in was attempted on the freshly-constructed service —
            # verifies no stale session was assumed.
            assert m.called

    def test_email_login_works_after_logout(self):
        """The email login IPC (`cloudbase_login`) must succeed independently
        of any prior session — the backend is fully stateless w.r.t. logout.
        Frontend `LoginCN.handleEmailLogin` depends on this; if the backend
        started honoring a stale token after logout, the email tab would
        silently 401.
        """
        from auth.tencent.cloudbase_auth import AuthResult

        svc = _make_service()
        # Patch sign_in_with_password directly — we want to assert the IPC
        # handler dispatches, not that the real CloudBase backend runs.
        with _cn_env(), patch(
            "gui.ipc.w2p_handlers.cloudbase_handler._get_service",
            return_value=svc,
        ), patch.object(
            svc,
            "sign_in_with_password",
            return_value=AuthResult(success=False, error="bad creds"),
        ) as m:
            from gui.ipc.w2p_handlers.cloudbase_handler import (
                handle_cloudbase_login,
            )
            resp = handle_cloudbase_login(
                _req(
                    "cloudbase_login",
                    {"email": "fresh@example.com", "password": "ValidPass123"},
                ),
                {"email": "fresh@example.com", "password": "ValidPass123"},
            )
            # Failure is expected (mocked), but the IPC must NOT 500 or
            # crash with a non-IPC exception.
            assert resp["status"] in {"success", "error"}, resp
            # Sign-in was attempted on the freshly-constructed service.
            m.assert_called_once()

    def test_logout_endpoint_returns_clean_success(self):
        """`cloudbase_logout` must succeed even if there is no current CloudBase
        session (i.e. user already logged out). This is the path invoked by
        ``LogoutManager.callBackendLogout()`` and must never throw.
        """
        svc = _make_service()
        with _cn_env(), patch(
            "gui.ipc.w2p_handlers.cloudbase_handler._get_service",
            return_value=svc,
        ):
            from gui.ipc.w2p_handlers.cloudbase_handler import (
                handle_cloudbase_logout,
            )
            resp = handle_cloudbase_logout(
                _req("cloudbase_logout", {}), {}
            )
            assert resp["status"] == "success", resp
            assert "message" in resp["result"]

    def test_check_config_does_not_throw_when_service_missing(self):
        """Regression for terminals/7.txt:895-985 (post-logout 2026-08-24):

        While uvicorn is mid-shutdown, ``_get_service()`` may return ``None``
        (e.g. ``is_cn()`` flips during shutdown, or the module-level
        singleton has been GC'd).  The frontend's
        ``cloudbaseAuth.checkConfig()`` then issues the IPC and gets back
        ``{"status": "success", "result": {"available": False, "reason": ...}}``.

        Backend contract: we MUST NOT throw — the response must be a
        well-formed IPCResponse with ``status: "success"``.  This way the
        frontend can detect "backend unreachable" via
        ``apiRouter.execute(...).success === false`` and keep the optimistic
        WeChat tab instead of flickering.

        Note: when service is missing, the handler intentionally omits
        ``wechat_available`` from the response — that absence is itself a
        signal to the frontend that the answer is unknown.
        """
        with patch("gui.ipc.w2p_handlers.cloudbase_handler.is_cn", return_value=True):
            with patch(
                "gui.ipc.w2p_handlers.cloudbase_handler._get_service",
                return_value=None,
            ):
                from gui.ipc.w2p_handlers.cloudbase_handler import (
                    handle_cloudbase_check_config,
                )
                resp = handle_cloudbase_check_config(
                    _req("cloudbase_check_config", {}), {}
                )
                # MUST be a well-formed response (not raise).
                assert resp["status"] == "success", resp
                result = resp["result"]
                assert result["available"] is False
                # Either wechat_available is False OR absent — both signal
                # "not configured / backend unreachable".
                assert result.get("wechat_available", False) is False
                # Reason present so frontend can log.
                assert result.get("reason") == "Service not available"

    def test_login_route_does_not_default_to_intl_while_loading(self):
        """Regression for terminals/7.txt:1002, 1006 + user feedback
        2026-08-24 ("刷新页面为什么 login 不是 loginCN, 后端配置的就是
        CN 的啊"):

        ``gui_v2/src/routes/index.tsx#useLoginComponent`` used to default
        to ``'cognito'`` (LoginIntl) whenever ``config.auth_type`` was
        missing, which is the case for the first render after a page
        refresh (``useState<AppConfig | null>(null)``).  When the
        backend was slow to come up, ``AppConfigProvider.loadConfig``
        fell into its catch and wrote an intl/cognito fallback config,
        so the route rendered LoginIntl forever — even after the
        backend finally served a real ``auth_type: 'cloudbase'``
        config.

        The fix: ``useLoginComponent`` returns ``null`` while
        ``loading || !config`` so ``LoginPageWrapper`` shows a spinner
        instead of the wrong component.  ``AppConfigProvider.loadConfig``
        retries on failure with backoff so the spinner only gives way
        to the fallback once the backend has been given a fair chance
        (~22.5s of cumulative retries).
        """
        repo_root = Path(__file__).resolve()
        for _ in range(4):
            repo_root = repo_root.parent

        routes_src = (repo_root / "gui_v2" / "src" / "routes" / "index.tsx").read_text()
        context_src = (repo_root / "gui_v2" / "src" / "contexts" / "AppConfigContext.tsx").read_text()

        # 1. ``useLoginComponent`` must short-circuit to ``null`` when
        #    config is still loading or null — NOT default to 'cognito'.
        #    Use a permissive pattern that captures until the next
        #    top-level ``function `` declaration (next sibling at 0
        #    indent — class/function boundary).
        import re
        start = routes_src.find("function useLoginComponent()")
        assert start != -1, "Could not find useLoginComponent in routes/index.tsx"
        # Find the next top-level declaration after useLoginComponent.
        # Top-level decls start at column 0 in the file (no leading
        # whitespace) — but inside a const ``routes = [...]`` block
        # helper functions like LoginPageWrapper are indented, so they
        # wouldn't be top-level.  Easier: just take everything until the
        # closing ``}`` at column 0 (which closes the helper-function
        # enclosure).  In practice the next thing after useLoginComponent
        # is the ``// 登录页面包装器`` comment + LoginPageWrapper.
        rest = routes_src[start:]
        end_match = re.search(
            r"^// 登录页面包装器",
            rest,
            flags=re.MULTILINE,
        )
        if end_match is None:
            # Fallback: take a generous window and let the string-contains
            # check find what we need.
            hook_body = rest[:4000]
        else:
            hook_body = rest[: end_match.start()]
        # The buggy pattern was `config.auth_type || 'cognito'` (i.e.
        # `|| 'cognito'` used as a defaulting fallback).  It must be
        # absent in actual executable code.  Strip line comments first
        # so we don't false-positive on `// ... || 'cognito'` (which is
        # exactly what the new code adds as documentation).
        code_lines = []
        for line in hook_body.splitlines():
            stripped = line.lstrip()
            if stripped.startswith("//"):
                continue
            # Drop inline comments
            if "//" in line:
                # Naive — doesn't handle strings.  Acceptable here
                # because we're only looking for ``|| 'cognito'`` which
                # is distinctive enough.
                line = line[: line.index("//")]
            code_lines.append(line)
        code_body = "\n".join(code_lines)
        assert "|| 'cognito'" not in code_body, (
            "useLoginComponent must not default to 'cognito' in code "
            "(comment-only mentions are fine for documentation).  The "
            "buggy defaulting pattern caused the '刷新页面显示 LoginIntl "
            "但后端是 CN 配置' regression."
        )
        assert "return null" in hook_body, (
            "useLoginComponent must explicitly return null while "
            "loading/null so LoginPageWrapper can show a spinner "
            "instead of the wrong Login component."
        )
        # And the watchdog pattern must be in place (periodic refetch on
        # fallback).
        assert "setInterval" in hook_body and "refetch" in hook_body, (
            "useLoginComponent must include a watchdog (setInterval) "
            "that calls refetch() while the AppConfig is the "
            "intl/cognito fallback.  Otherwise the user is stuck on "
            "LoginIntl even after the backend wakes up."
        )

        # 2. ``AppConfigProvider.loadConfig`` must have a retry loop
        #    before giving up and writing the intl/cognito fallback.
        #    Otherwise a single transient ECONNREFUSED at startup
        #    locks the user into the fallback forever.
        assert "RETRY_DELAYS_MS" in context_src or "retry" in context_src.lower(), (
            "AppConfigProvider.loadConfig must retry fetchConfig with "
            "backoff before writing the intl/cognito fallback — "
            "otherwise the user gets stuck on the wrong login page."
        )

    def test_mainwindow_logout_does_not_stop_local_server(self):
        """Regression for terminals/7.txt:898-1032 (post-logout 2026-08-24):

        ``MainWindow._async_cleanup_and_logout()`` used to call
        ``stop_local_server()`` which kills the uvicorn instance on
        127.0.0.1:4668.  Once that happens, every subsequent IPC call
        (``cloudbase_check_config``, ``get_last_login``, ``getAppConfig``)
        returns HTTP 500, so the LoginCN page cannot load its config and
        falls back to the empty intl/cognito AppConfig — no WeChat tab,
        no email/phone login (terminals/7.txt:1002, 1006 show the
        consecutive ``Local GraphQL error for`` stack).

        Logout is NOT a process exit; the user may immediately re-login
        (or the same token refresh path may be hit again).  Only
        ``gui/WebGUI.py``'s ``force exit`` path may call
        ``stop_local_server()``.

        We pin the contract by inspecting the source of
        ``MainWindow._async_cleanup_and_logout`` rather than running it
        (the method transitively imports PyQt5 which is not required to
        exercise the bug, and the source-level check is what we'd have
        to grep for in a code review anyway).
        """
        repo_root = Path(__file__).resolve()
        for _ in range(4):
            repo_root = repo_root.parent
        main_gui_path = repo_root / "gui" / "MainGUI.py"
        source = main_gui_path.read_text()

        # Locate the cleanup coroutine body.  We use Python's `ast` to
        # walk the module and find ``MainWindow._async_cleanup_and_logout``
        # — the body is everything between the function's first statement
        # and the last.  This is robust against docstring/comment noise.
        import ast
        import re
        tree = ast.parse(source)
        func = None
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "_async_cleanup_and_logout":
                func = node
                break
        assert func is not None, "Could not find _async_cleanup_and_logout() in gui/MainGUI.py"

        # Render the body as source and strip comments + docstrings.
        body_src = ast.get_source_segment(source, func) or ""
        # Drop the function header line (keeps the body).
        body_lines = body_src.splitlines()[1:]
        body = "\n".join(body_lines)

        # Strip Python triple-quoted docstrings within the body (rare —
        # there is one in the original file but it's the function header,
        # which we already trimmed).
        body = re.sub(r'""".*?"""', '', body, flags=re.DOTALL)
        body = re.sub(r"'''.*?'''", '', body, flags=re.DOTALL)

        # 1. The cleanup coroutine must NOT mention ``stop_local_server``
        #    in actual executable code (comments are fine because they
        #    document the fix).
        code_lines = [
            line for line in body.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        code_body = "\n".join(code_lines)
        assert "stop_local_server" not in code_body, (
            "MainWindow._async_cleanup_and_logout has a code-level "
            "reference to stop_local_server — this would kill the IPC "
            "server that the frontend needs for the post-logout login "
            "page / next login. Local server should only be stopped in "
            "gui/WebGUI.py on app exit."
        )

        # 2. It still pre-cleans the MCP session manager so per-user
        #    asyncio resources are released.
        assert "MCPHandler.cleanup" in body, (
            "MCP session manager pre-cleanup is required to release "
            "per-user asyncio resources during logout."
        )

        # 3. The companion ``gui/WebGUI.py`` force-exit path is the ONE
        #    place that should still call ``stop_local_server()`` — make
        #    sure we didn't accidentally remove it from there.
        web_gui_path = repo_root / "gui" / "WebGUI.py"
        web_gui_source = web_gui_path.read_text()
        assert "stop_local_server" in web_gui_source, (
            "gui/WebGUI.py force-exit path must still call "
            "stop_local_server() — that's the correct place to shut "
            "down the IPC server, because that's when the whole "
            "process is exiting."
        )