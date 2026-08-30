"""
CloudBase Authentication IPC Handler
腾讯云 CloudBase 认证 IPC 处理器

仅在 CN 版本（ECAN_APP_ID=cn）时可用。
"""

import os
import traceback
import uuid
from typing import Any, Dict, Optional

import requests

from utils.app_env import is_cn, get_app_id
from auth.tencent import (
    get_cloudbase_service,
    CloudBaseUserInfo,
)
from auth.auth_messages import auth_messages
from gui.ipc.handlers import validate_params
from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import (
    IPCRequest,
    IPCResponse,
    create_error_response,
    create_success_response,
)
from utils.logger_helper import logger_helper as logger


def _get_service():
    """获取 CloudBase 服务"""
    if not is_cn():
        return None
    try:
        return get_cloudbase_service()
    except Exception as e:
        logger.error(f"[CloudBaseHandler] Failed to get service: {e}")
        return None


# ============================================================
# 错误码映射
# ============================================================

ERROR_CODE_MAP = {
    "INVALID_CREDENTIALS": "login_invalid_credentials",
    "USER_NOT_FOUND": "login_invalid_credentials",
    "WEAK_PASSWORD": "signup_invalid_password",
    "USER_ALREADY_EXISTS": "signup_user_exists",
    "INVALID_CODE": "confirm_forgot_invalid_code",
    "EXPIRED_CODE": "confirm_forgot_expired_code",
    "COOLDOWN": "code_cooldown",
    "SMS_SEND_FAILED": "sms_send_failed",
    "NOT_CONFIGURED": "cloudbase_not_configured",
}


def _localized_error(error_code: Optional[str], default_key: str) -> str:
    """将错误码映射到本地化消息"""
    key = ERROR_CODE_MAP.get(error_code or "", default_key)
    return auth_messages.get_message(key)


def _build_error_response(request: IPCRequest, code: str,
                          auth_result, default_key: str = "login_failed",
                          fallback_message: Optional[str] = None) -> IPCResponse:
    """Build a localized error response while preserving the original CloudBase error
    in `details` so the frontend can surface it for debugging.

    Args:
        request: original IPC request
        code: IPC-level error code (e.g. "LOGIN_FAILED")
        auth_result: CloudBaseAuthService result with .error / .error_code
        default_key: i18n key when no specific code mapping exists
        fallback_message: optional override for the user-facing message
    """
    raw_message = auth_result.error if isinstance(auth_result.error, str) else None
    raw_code = getattr(auth_result, "error_code", None)
    user_message = fallback_message or _localized_error(raw_code, default_key)
    return create_error_response(
        request, code, user_message,
        details={
            "original_error": raw_message,
            "original_error_code": raw_code,
        },
    )


def _get_endpoint_config_for_settings() -> Optional[Dict[str, str]]:
    """Get CN (TCB) endpoint config for general_settings, or None if not CN."""
    try:
        from agent.cloud_api.endpoints import get_endpoint_config
        cfg = get_endpoint_config()
        if not cfg.is_cn:
            return None
        return {
            "wan_api_endpoint": cfg.graphql_endpoint,
            "ws_api_endpoint": cfg.ws_endpoint,  # WS endpoint (TCS WS service for CN)
            "ws_api_host": cfg.host,
        }
    except Exception:
        return None


def _apply_endpoints_to_general_settings(gs, cfg_ep: Dict[str, str]) -> bool:
    """Apply TCB endpoints to general_settings. Returns True if any value changed."""
    changed = False
    if gs.wan_api_endpoint != cfg_ep.get("wan_api_endpoint"):
        gs.wan_api_endpoint = cfg_ep.get("wan_api_endpoint", "")
        changed = True
    if gs.ws_api_endpoint != cfg_ep.get("ws_api_endpoint"):
        gs.ws_api_endpoint = cfg_ep.get("ws_api_endpoint", "")
        changed = True
    if gs.ws_api_host != cfg_ep.get("ws_api_host"):
        gs.ws_api_host = cfg_ep.get("ws_api_host", "")
        changed = True
    if changed:
        logger.info(
            f"[_apply_endpoints_to_general_settings] Updated endpoints: "
            f"wan={gs.wan_api_endpoint}, ws={gs.ws_api_endpoint}, host={gs.ws_api_host}"
        )
    return changed


def _ensure_cloud_account(access_token: str, user_info: "CloudBaseUserInfo",
                          login_type: str) -> None:
    """Best-effort: make sure the CN ``accounts`` table has a row for this user.

    2026-08-29: the CN ``llm_proxy`` authorizes proxied LLM calls against
    ``public.accounts.subs``, so an email/phone login whose account row is
    missing must get one created at login time. POSTs an ``ensure_account``
    event to the ``ecbAccountManager`` SCF route (same TCB origin as the
    GraphQL endpoint).

    Contract (deployed server, 2026-08-29): the CloudBase public Event
    gateway STRIPS the Authorization header on this route, so the fresh
    CloudBase access token travels in the JSON body as ``accessToken``. The
    server verifies it directly with CloudBase ``/auth/v1/user/me`` and
    derives the real subject/email/phone from there — it does not trust any
    caller-provided identity fields, so none are sent.

    Fire-and-forget in a daemon thread: login must never block or fail on
    this. Any non-200 is logged as WARNING.
    """
    def _do():
        try:
            import json as _json
            import urllib.request as _rq
            import urllib.error as _err
            from urllib.parse import urlsplit

            from agent.cloud_api.endpoints import get_endpoint_config
            gql = (get_endpoint_config().graphql_endpoint or "").strip()
            if not gql:
                logger.warning("[EnsureAccount] no GraphQL endpoint configured — skipped")
                return
            parts = urlsplit(gql)
            url = f"{parts.scheme}://{parts.netloc}/ecbAccountManager"

            body = {
                "action": "ensure_account",
                "provider": login_type,
                "accessToken": access_token,
            }
            req = _rq.Request(
                url,
                data=_json.dumps(body).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            # Local identifier for log correlation only — never sent to the
            # server (it derives identity from the verified token).
            who = user_info.email or user_info.phone_number or user_info.sub or "?"
            try:
                with _rq.urlopen(req, timeout=15) as resp:
                    raw = resp.read(2048).decode("utf-8", "replace")
                    logger.info(
                        f"[EnsureAccount] ensure_account user={who!r} "
                        f"status={resp.status} resp={raw[:300]}"
                    )
            except _err.HTTPError as he:
                raw = he.read(1024).decode("utf-8", "replace")
                logger.warning(
                    f"[EnsureAccount] ensure_account user={who!r} "
                    f"HTTP {he.code}: {raw[:300]}"
                )
        except Exception as exc:
            logger.warning(f"[EnsureAccount] ensure_account skipped: {exc}")

    try:
        import threading
        threading.Thread(target=_do, daemon=True, name="cn-ensure-account").start()
    except Exception as exc:
        logger.warning(f"[EnsureAccount] thread start failed: {exc}")


def _build_login_response(request: IPCRequest, token: str,
                          refresh_token: str,
                          user_info: CloudBaseUserInfo,
                          machine_role: str = "Commander",
                          login_type: str = "password") -> IPCResponse:
    """Build a successful login response.

    Drives the same post-login flow as the Intl handler:

    1. Install CloudBase tokens into ``AuthManager`` so ``token_manager``,
       ``start_refresh_task`` and ``MainWindow`` see a signed-in user.
    2. Call ``Login.handleLogin`` to schedule the unified
       MainWindow / IPC-token / onboarding launch chain.
    3. Mint an IPC session token (web mode: also create a web session).
    4. Return the same ``{token, user_info, session_id, message}`` shape
       that ``user_handler._build_user_info_response`` returns on Intl —
       so the CN frontend can stay response-shape-identical.

    Args:
        request:        original IPC request
        token:          CloudBase access_token
        refresh_token:  CloudBase refresh_token (may be empty for some flows)
        user_info:      ``CloudBaseUserInfo`` from the upstream API
        machine_role:   machine role to attach to the user (default Commander)
        login_type:     one of ``"password"``, ``"phone"``, ``"wechat"``
    """
    logger.info(
        f"[_build_login_response] ENTRY: token_len={len(token) if token else 0}, "
        f"refresh_token_len={len(refresh_token) if refresh_token else 0}, "
        f"machine_role={machine_role!r}, login_type={login_type!r}, "
        f"user_identifier_email={user_info.email!r}"
    )
    try:
        from app_context import AppContext
        login = AppContext.get_login()
    except Exception as e:
        logger.warning(f"[CloudBaseLogin] AppContext.get_login unavailable: {e}")
        login = None

    user_identifier = (
        user_info.email
        or user_info.phone_number
        or user_info.username
        or user_info.sub
        or "unknown"
    )

    # For password login flows the password was provided by the user;
    # for OTP/phone/wechat flows it's empty. We forward whatever we have
    # so ``AuthManager.complete_login_from_provider`` can persist it via
    # ``_update_saved_login_info`` (keyring entry + uli.json).
    # NOTE: ``request`` is a ``TypedDict`` (a plain ``dict`` at runtime),
    # so we must use dict-style access — ``getattr(request, "params")``
    # always returns ``None`` and silently drops the password.
    forwarded_password = ""
    request_params = request.get("params") if isinstance(request, dict) else None
    if isinstance(request_params, dict):
        forwarded_password = request_params.get("password", "") or ""

    # Step 1: install tokens into AuthManager — single source of truth for
    # subsequent MainWindow / token_manager / refresh loop.
    auth_result: Optional[Dict[str, Any]] = None
    login_is_none = login is None
    login_auth_mgr_none = (getattr(login, "auth_manager", None) is None) if login is not None else True
    if login_is_none or login_auth_mgr_none:
        logger.warning(
            f"[_build_login_response] Skipping complete_login_from_provider: "
            f"login is None={login_is_none}, "
            f"login.auth_manager is None={login_auth_mgr_none}"
        )
    if login is not None and getattr(login, "auth_manager", None) is not None:
        try:
            logger.info(
                f"[_build_login_response] Calling complete_login_from_provider: "
                f"user_identifier={user_identifier!r}, "
                f"forwarded_password_len={len(forwarded_password)}, "
                f"refresh_token_len={len(refresh_token) if refresh_token else 0}"
            )
            auth_result = login.auth_manager.complete_login_from_provider(
                access_token=token,
                refresh_token=refresh_token or None,
                expires_in=7200,
                user_identifier=user_identifier,
                role=machine_role,
                password=forwarded_password,
                user_profile={
                    "username": user_identifier,
                    "email": user_info.email or "",
                    "phone_number": user_info.phone_number or "",
                    "sub": user_info.sub or "",
                    "name": user_info.nickname or "",
                    "given_name": "",
                    "family_name": "",
                    "picture": user_info.avatar_url or "",
                    "email_verified": bool(user_info.email),
                    "login_type": login_type,
                },
            )
            # Never stringify auth_result here: it contains live access and
            # refresh tokens.  The old log line leaked both credentials into
            # ordinary support logs.
            result_data = auth_result.get("data", {}) if isinstance(auth_result, dict) else {}
            logger.info(
                "[_build_login_response] complete_login_from_provider returned: "
                "success=%s, user_identifier=%r, token_keys=%s",
                auth_result.get("success") if isinstance(auth_result, dict) else False,
                result_data.get("user_identifier"),
                sorted((result_data.get("tokens") or {}).keys()),
            )
        except Exception as e:
            logger.error(
                f"[CloudBaseLogin] complete_login_from_provider failed: {e}",
                exc_info=True,
            )

    # Step 1.25: server-side account provisioning. WeChat logins get their
    # accounts row from the PHP-callback/wechat provision path; email/phone
    # logins had NO creation path, leaving llm_proxy authorization (which
    # reads public.accounts.subs) to fail for fresh accounts. Best-effort,
    # background — see _ensure_cloud_account.
    if login_type in ("password", "phone") and token:
        _ensure_cloud_account(token, user_info, login_type)

    # Step 1.5: tell SessionSupervisor the fresh token is installed.
    #
    # Without this, ``_last_token_installed_at`` stays at its constructor
    # default of 0 and the supervisor's fresh-token grace guard in
    # ``_drive_silent_refresh`` never fires — so a 401 returned by the
    # AppSync edge 30-60s after login (CloudBase upstream cache lag)
    # causes an unconditional on_session_expired + GUI logout. Notifying
    # here is the IPC-path equivalent of LoginoutGUI._run() line 349.
    if (
        login is not None
        and getattr(login, "session_supervisor", None) is not None
    ):
        try:
            login.session_supervisor.notify_token_installed()
            logger.debug(
                "[_build_login_response] notified SessionSupervisor of "
                "freshly installed token"
            )
        except Exception as _sup_exc:
            logger.debug(
                f"[_build_login_response] supervisor notify_token_installed "
                f"skipped: {_sup_exc}"
            )

    # Step 2: update general_settings endpoints for CN (TCB) so
    # PassiveCommandService / AppSyncPassiveClient / other components
    # that read from general_settings get the correct TCB URLs instead
    # of the hardcoded AWS AppSync URLs from settings_template.json.
    # NOTE: main_window.config_manager is only available after MainWindow is created,
    # so this update happens in two phases: (a) store in AppContext for later use,
    # (b) apply when MainWindow is available (via Login._launch_main_window hook).
    try:
        from app_context import AppContext
        cfg_ep = _get_endpoint_config_for_settings()
        if cfg_ep:
            # Store in AppContext for later application in _launch_main_window
            AppContext()._pending_tcb_endpoints = cfg_ep
            logger.info(
                f"[_build_login_response] Stored pending TCB endpoints for later: "
                f"wan={cfg_ep['wan_api_endpoint']}, "
                f"ws={cfg_ep['ws_api_endpoint']}, "
                f"host={cfg_ep['ws_api_host']}"
            )
            # Also try to apply immediately if MainWindow is already available
            # (shouldn't happen in normal flow, but defensive)
            mainwin = AppContext.get_main_window()
            if mainwin and hasattr(mainwin, 'config_manager'):
                _apply_endpoints_to_general_settings(mainwin.config_manager.general_settings, cfg_ep)
    except Exception as e:
        logger.warning(f"[_build_login_response] Failed to update endpoints: {e}")

    # Step 3: trigger the unified Intl post-login chain.
    #
    # IMPORTANT: We deliberately do NOT call ``login.handleLogin(...)`` here.
    # ``handleLogin`` routes through ``_handle_login`` which calls
    # ``self.auth_manager.login(u, p)`` — that re-runs the upstream auth
    # provider with the (empty) password, which 401s on CN. The session is
    # already established by ``complete_login_from_provider`` above, so we
    # instead invoke the same MainWindow / token_manager / onboarding path
    # explicitly, matching the body of ``_handle_login`` minus the re-auth.
    session_token = ""
    session_id: Optional[str] = None
    if login is not None:
        try:
            from gui.ipc.token_manager import token_manager
            session_token = token_manager.generate_token(user_identifier, machine_role)
            logger.info(f"[CloudBaseLogin] IPC session token generated for {user_identifier}")
        except Exception as e:
            logger.warning(f"[CloudBaseLogin] token_manager.generate_token failed: {e}")

        try:
            from gui.ipc.w2p_handlers.user_handler import (
                _create_web_session,
            )
            session_id = _create_web_session(
                user_identifier,
                {
                    "email": user_info.email or user_identifier,
                    "role": machine_role,
                    "login_type": login_type,
                },
                auth_token=session_token or token,
            )
        except Exception as e:
            logger.debug(f"[CloudBaseLogin] _create_web_session skipped: {e}")

        # Drive the MainWindow launch chain (desktop mode) or just mark
        # the login progress complete (web mode). Mirrors the body of
        # ``Login._handle_login`` minus the ``auth_manager.login`` call.
        if os.getenv("ECAN_MODE", "desktop") == "web":
            try:
                login._update_progress(100, "Web session ready")
            except Exception as e:
                logger.debug(f"[CloudBaseLogin] _update_progress skipped: {e}")
        else:
            try:
                from gui.LoginoutGUI import LoginRequest, LoginType
                launch_request = LoginRequest(
                    LoginType.USERNAME_PASSWORD,
                    username=user_identifier,
                    password="",
                    role=machine_role,
                    schedule_mode="manual",
                )
                loop = AppContext.main_loop
                if loop and loop.is_running():
                    import asyncio as _asyncio
                    _asyncio.run_coroutine_threadsafe(
                        login._async_launch_main_window(launch_request),
                        loop,
                    )
                    logger.info("[CloudBaseLogin] MainWindow launch task scheduled")
                else:
                    logger.error(
                        "[CloudBaseLogin] Main event loop not running; "
                        "MainWindow launch skipped"
                    )
            except Exception as e:
                logger.error(f"[CloudBaseLogin] MainWindow launch dispatch failed: {e}")

        # Trigger onboarding check — same as Intl.
        try:
            config_manager = AppContext.get_config_manager()
            if config_manager and hasattr(config_manager, "llm_manager"):
                config_manager.llm_manager.reset_onboarding_flag()
                try:
                    import asyncio as _asyncio
                    loop = _asyncio.get_running_loop()
                    loop.create_task(
                        config_manager.llm_manager.check_and_show_onboarding(
                            delay_seconds=3.0,
                            force_check=False,
                        )
                    )
                    logger.debug("[CloudBaseLogin] Scheduled onboarding check")
                except RuntimeError:
                    logger.debug("[CloudBaseLogin] No event loop for onboarding check")
        except Exception as e:
            logger.debug(f"[CloudBaseLogin] Could not schedule onboarding check: {e}")

    # Step 3: build the response in the same shape Intl's
    # ``_build_user_info_response`` produces — frontend can stay unchanged.
    response_data: Dict[str, Any] = {
        "token": session_token or token,
        "refresh_token": refresh_token or token,
        "message": auth_messages.get_message("login_success"),
        "user_info": {
            "username": user_identifier,
            "email": user_info.email or "",
            "phone": user_info.phone_number or "",
            "role": machine_role,
            "name": user_info.nickname or "",
            "given_name": "",
            "family_name": "",
            "picture": user_info.avatar_url or "",
            "email_verified": bool(user_info.email),
            "login_type": login_type,
            "uuid": user_info.sub or "",
        },
    }
    if session_id:
        response_data["session_id"] = session_id

    logger.info(
        f"[_build_login_response] EXIT: building success response, "
        f"response_keys={list(response_data.keys())}, "
        f"session_token_present={bool(session_token)}, session_id={session_id!r}"
    )
    return create_success_response(request, response_data)


# ============================================================
# 邮箱注册
# ============================================================

@IPCHandlerRegistry.handler("cloudbase_signup")
def handle_cloudbase_signup(request: IPCRequest,
                            params: Optional[Dict[str, Any]]) -> IPCResponse:
    """CloudBase 邮箱注册

    CloudBase 不支持直接 email+password 注册,必须走邮箱验证码流程。
    后端自动完成: 发验证码 → 验证 → 注册,用户无感知。

    请求参数:
        email    (必填): 邮箱地址
        password (必填): 密码
        username (可选): 用户名,默认用 email 前缀
    """
    lang = auth_messages.DEFAULT_LANG
    try:
        is_valid, data, error = validate_params(params, ["email", "password"])
        if not is_valid:
            return create_error_response(
                request, "INVALID_PARAMS",
                "email and password are required",
            )

        email = data["email"].strip().lower()
        password = data["password"]
        # CloudBase Username 必须符合正则: ^[a-z][0-9a-z_-]{5,24}$
        # 邮箱前缀可能是数字开头(如 1050588178@qq.com)，需要处理
        raw_username = data.get("username", "").strip() or email.split("@")[0]
        # 确保 username 以小写字母开头
        if raw_username and raw_username[0].isdigit():
            raw_username = "user_" + raw_username
        # 只保留有效字符（小写字母、数字、下划线、连字符），截取到最大长度 24
        import re
        clean_username = re.sub(r'[^a-z0-9_-]', '', raw_username.lower())
        if len(clean_username) > 24:
            clean_username = clean_username[:24]
        # 确保最小长度 6（正则要求的最小长度）
        if len(clean_username) < 6:
            clean_username = clean_username + "12345"[:6 - len(clean_username)]
        # 确保以小写字母开头
        if clean_username and not clean_username[0].isalpha():
            clean_username = "u" + clean_username
        username = clean_username
        lang = data.get("lang", auth_messages.DEFAULT_LANG)
        auth_messages.set_language(lang)
        logger.info(f"[CloudBaseSignup] Generated username: {username} from email: {email}")

        service = _get_service()
        if not service:
            return create_error_response(
                request, "CLOUDBASE_NOT_AVAILABLE",
                auth_messages.get_message("cloudbase_not_available"),
            )

        # CloudBase target=ANY 对新旧邮箱都发验证码
        # 响应里的 is_user 字段告诉我们: true=已注册, false/None=新用户
        logger.info(f"[CloudBaseSignup] Sending verification code to: {email}")
        send_result = service.send_verification_code(email=email)
        if not send_result.success:
            logger.warning(f"[CloudBaseSignup] Send code failed: {send_result.error}")
            return _build_error_response(request, "SEND_CODE_FAILED",
                                          send_result, default_key="signup_failed")

        is_user = send_result.data.get("is_user")
        if is_user:
            return create_error_response(
                request, "USER_EXISTS",
                "This email is already registered. Please log in instead.",
            )

        # CloudBase 在不同响应包装下会用两种字段名 (``verification_id`` vs ``verificationId``)
        verification_id = (
            (send_result.data.get("verification_id") or "")
            or (send_result.data.get("verificationId") or "")
        )
        if not verification_id:
            # 没有 verification_id 意味着后续 verify 步骤无法进行，
            # 应当明确报错而不是返回假 success 让前端显示"验证码已发送"。
            logger.warning(
                f"[CloudBaseSignup] send_verification_code returned no verification_id: "
                f"email={email}, data_keys={list(send_result.data.keys())}"
            )
            return create_error_response(
                request, "SEND_CODE_FAILED",
                "Failed to obtain verification_id from CloudBase. Please retry.",
            )

        return create_success_response(request, {
            "pending_verification": True,
            "message": auth_messages.get_message("signup_code_sent") or "Verification code sent to your email",
            "verification_id": verification_id,
            "email": email,
        })

    except Exception as e:
        logger.error(f"[CloudBaseSignup] Error: {e}\n{traceback.format_exc()}")
        auth_messages.set_language(lang)
        return create_error_response(
            request, "SIGNUP_ERROR",
            auth_messages.get_message("signup_failed"),
        )


@IPCHandlerRegistry.handler("cloudbase_signup_confirm")
def handle_cloudbase_signup_confirm(request: IPCRequest,
                                    params: Optional[Dict[str, Any]]) -> IPCResponse:
    """CloudBase 邮箱注册 - 确认验证码并完成注册

    前端收到 pending_verification 响应后,展示"输入验证码"表单,
    用户填入验证码后调用此接口完成注册。

    请求参数:
        email           (必填): 邮箱地址
        code            (必填): 邮箱收到的 6 位验证码
        verification_id  (必填): cloudbase_signup 返回的 verification_id
        password        (可选): 密码(首次 signup 传了则用那个)
        username        (可选): 用户名
    """
    lang = auth_messages.DEFAULT_LANG
    try:
        is_valid, data, error = validate_params(params, ["email", "code", "verification_id"])
        if not is_valid:
            return create_error_response(
                request, "INVALID_PARAMS",
                "email, code and verification_id are required",
            )

        email = data["email"].strip().lower()
        code = data["code"].strip()
        verification_id = data["verification_id"].strip()
        password = data.get("password", "")
        # CloudBase Username 必须符合正则: ^[a-z][0-9a-z_-]{5,24}$
        # 邮箱前缀可能是数字开头(如 1050588178@qq.com)，需要处理
        import re as regex_module
        raw_username = data.get("username", "").strip() or email.split("@")[0]
        # 确保 username 以小写字母开头
        if raw_username and raw_username[0].isdigit():
            raw_username = "user_" + raw_username
        # 只保留有效字符（小写字母、数字，下划线、连字符），截取到最大长度 24
        clean_username = regex_module.sub(r'[^a-z0-9_-]', '', raw_username.lower())
        if len(clean_username) > 24:
            clean_username = clean_username[:24]
        # 确保最小长度 6（正则要求的最小长度）
        if len(clean_username) < 6:
            clean_username = clean_username + "12345"[:6 - len(clean_username)]
        # 确保以小写字母开头
        if clean_username and not clean_username[0].isalpha():
            clean_username = "u" + clean_username
        username = clean_username
        lang = data.get("lang", auth_messages.DEFAULT_LANG)
        auth_messages.set_language(lang)
        logger.info(f"[CloudBaseSignupConfirm] Generated username: {username} from email: {email}")

        service = _get_service()
        if not service:
            return create_error_response(
                request, "CLOUDBASE_NOT_AVAILABLE",
                auth_messages.get_message("cloudbase_not_available"),
            )

        # 验证验证码,获取 verification_token
        logger.info(f"[CloudBaseSignupConfirm] Verifying code for: {email}")
        verify_result = service.verify_verification_code(verification_id, code)
        if not verify_result.success:
            logger.warning(f"[CloudBaseSignupConfirm] Verify failed: {verify_result.error}")
            return _build_error_response(request, "VERIFY_FAILED",
                                          verify_result, default_key="signup_failed")

        verification_token = verify_result.data.get("verification_token", "")

        # 用 verification_token 完成注册
        logger.info(f"[CloudBaseSignupConfirm] Completing registration: {email}")
        signup_result = service.sign_up_with_otp(
            email=email,
            verification_token=verification_token,
            username=username,
            password=password,
        )

        if not signup_result.success:
            logger.warning(f"[CloudBaseSignupConfirm] Failed: {signup_result.error}")
            return _build_error_response(request, "SIGNUP_FAILED",
                                          signup_result, default_key="signup_failed")

        # 注册成功后自动登录
        return _build_login_response(
            request,
            token=signup_result.data["access_token"],
            refresh_token=signup_result.data["refresh_token"],
            user_info=CloudBaseUserInfo(**{
                k: v for k, v in signup_result.data["user_info"].items()
                if k in CloudBaseUserInfo.__dataclass_fields__
            }),
            machine_role=data.get("role", "Commander"),
            login_type="password",
        )

    except Exception as e:
        logger.error(f"[CloudBaseSignupConfirm] Error: {e}\n{traceback.format_exc()}")
        auth_messages.set_language(lang)
        return create_error_response(
            request, "SIGNUP_ERROR",
            auth_messages.get_message("signup_failed"),
        )


# ============================================================
# 邮箱登录
# ============================================================

@IPCHandlerRegistry.handler("cloudbase_login")
def handle_cloudbase_login(request: IPCRequest,
                           params: Optional[Dict[str, Any]]) -> IPCResponse:
    """CloudBase 邮箱登录"""
    lang = auth_messages.DEFAULT_LANG
    try:
        is_valid, data, error = validate_params(params, ["email", "password"])
        if not is_valid:
            return create_error_response(request, "INVALID_PARAMS", error)

        email = data["email"].strip().lower()
        password = data["password"]
        machine_role = data.get("role", "Commander")
        lang = data.get("lang", auth_messages.DEFAULT_LANG)
        auth_messages.set_language(lang)

        service = _get_service()
        if not service:
            return create_error_response(
                request, "CLOUDBASE_NOT_AVAILABLE",
                auth_messages.get_message("cloudbase_not_available"),
            )

        logger.info(f"[CloudBaseLogin] Email login for: {email} role={machine_role}")
        result = service.sign_in_with_password(email, password)
        logger.info(
            f"[CloudBaseLogin] sign_in_with_password returned: "
            f"success={result.success}, "
            f"has_access_token={bool(result.data and result.data.get('access_token'))}, "
            f"has_refresh_token={bool(result.data and result.data.get('refresh_token'))}, "
            f"error={result.error!r}, error_code={result.error_code!r}"
        )

        if not result.success:
            if result.error_code == "NOT_CONFIGURED":
                return create_error_response(
                    request, "CLOUDBASE_NOT_AVAILABLE",
                    auth_messages.get_message("cloudbase_not_available"),
                )
            logger.warning(f"[CloudBaseLogin] Failed for {email}: {result.error}")
            return _build_error_response(request, "LOGIN_FAILED",
                                          result, default_key="login_failed")

        # /auth/v1/signin 响应不含 email，先用初始 user_info
        user_info = CloudBaseUserInfo(**{
            k: v for k, v in result.data["user_info"].items()
            if k in CloudBaseUserInfo.__dataclass_fields__
        })
        logger.info(
            f"[CloudBaseLogin] Built initial user_info: "
            f"sub={user_info.sub!r}, email={user_info.email!r}, "
            f"phone={user_info.phone_number!r}, username={user_info.username!r}"
        )

        # 补全：调 /auth/v1/user/me 获取完整用户信息（含 email、username 等）
        logger.info(f"[CloudBaseLogin] Calling get_current_user (/auth/v1/user/me)")
        me = service.get_current_user(result.data["access_token"])
        logger.info(
            f"[CloudBaseLogin] get_current_user returned: success={me.success}, "
            f"keys={list(me.data.keys()) if isinstance(me.data, dict) else None}, "
            f"error={me.error!r}"
        )
        if me.success:
            ui = me.data
            # 优先级：已知信息 > /user/me 返回值
            user_info.sub = ui.get("sub") or ui.get("user_id") or user_info.sub
            if not user_info.email:
                user_info.email = ui.get("email") or None
            if not user_info.phone_number:
                user_info.phone_number = ui.get("phone_number") or None
            if not user_info.username:
                user_info.username = ui.get("username") or ui.get("name") or None
            if not user_info.nickname:
                user_info.nickname = ui.get("name") or None

        return _build_login_response(
            request,
            token=result.data["access_token"],
            refresh_token=result.data["refresh_token"],
            user_info=user_info,
            machine_role=machine_role,
            login_type="password",
        )

    except Exception as e:
        logger.error(f"[CloudBaseLogin] Error: {e}\n{traceback.format_exc()}")
        auth_messages.set_language(lang)
        return create_error_response(
            request, "LOGIN_ERROR",
            auth_messages.get_message("login_failed"),
        )


def _save_cloudbase_credentials(email: str, password: str, role: str,
                                refresh_token: Optional[str] = None) -> None:
    """Save CloudBase login credentials to keyring and uli.json (mirrors AWS pattern).

    Uses keyring directly to avoid importing AuthManager (which imports CognitoService → jose).
    """
    import json
    import keyring
    from config.envi import getECBotDataHome

    try:
        # 1. Store password in keyring
        keyring.set_password("ecan_cloudbase_auth", email, password)

        # 2. Store refresh_token in keyring (separate service, same keyring)
        if refresh_token:
            keyring.set_password("ecan_cloudbase_refresh", email, refresh_token)

        # 3. Write uli.json (username + role)
        ecb_home = getECBotDataHome()
        acct_file = ecb_home + "/uli.json"
        data = {}
        if os.path.exists(acct_file):
            try:
                with open(acct_file, 'r') as f:
                    data = json.load(f)
            except Exception:
                pass
        data["user"] = email
        data["machine_role"] = role
        with open(acct_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.debug(f"[_save_cloudbase_credentials] Saved for: {email}")
    except Exception as e:
        logger.warning(f"[_save_cloudbase_credentials] Failed: {e}")


# ============================================================
# 发送手机验证码
# ============================================================

@IPCHandlerRegistry.handler("cloudbase_send_code")
def handle_cloudbase_send_code(request: IPCRequest,
                              params: Optional[Dict[str, Any]]) -> IPCResponse:
    """发送验证码（支持手机号或邮箱）"""
    try:
        phone = params.get("phone", "").strip() if params.get("phone") else ""
        email = params.get("email", "").strip().lower() if params.get("email") else ""
        purpose = (params.get("purpose", "login") or "login") if params else "login"
        lang = (params.get("lang", auth_messages.DEFAULT_LANG) or auth_messages.DEFAULT_LANG) if params else auth_messages.DEFAULT_LANG
        auth_messages.set_language(lang)

        if not phone and not email:
            return create_error_response(request, "INVALID_PARAMS",
                "phone or email is required")

        if phone and email:
            return create_error_response(request, "INVALID_PARAMS",
                "only phone OR email, not both")

        service = _get_service()
        if not service:
            return create_error_response(
                request, "CLOUDBASE_NOT_AVAILABLE",
                auth_messages.get_message("cloudbase_not_available"),
            )

        if phone:
            logger.info(f"[CloudBaseSendCode] Sending code to: {phone[:3]}****, purpose: {purpose}")
            result = service.send_verification_code(phone_number=phone)
        else:
            logger.info(f"[CloudBaseSendCode] Sending code to: {email}, purpose: {purpose}")
            result = service.send_verification_code(email=email)

        if not result.success:
            logger.warning(f"[CloudBaseSendCode] Failed: {result.error}")
            return _build_error_response(request, "SEND_CODE_FAILED",
                                          result, default_key="sms_send_failed")

        response_data: Dict[str, Any] = {
            "message": auth_messages.get_message("code_sent"),
            "type": "phone" if phone else "email",
        }
        # 开发模式：返回验证码便于测试
        if result.data and result.data.get("dev_code"):
            response_data["dev_code"] = result.data["dev_code"]
        # 邮箱/手机模式返回 verification_id（后续需用户输入验证码来换 token）
        # CloudBase 在不同响应包装下会用两种字段名，这里兼容两种
        if result.data and result.data.get("verification_id"):
            response_data["verification_id"] = result.data["verification_id"]
        # 透传 is_user：让前端知道号码/邮箱是否已注册，可用于"智能登录/注册"流程
        # (方案 C: 不区分 login/signup UI，后端自动决定走 sign_in 还是 sign_up)
        if result.data and "is_user" in result.data:
            response_data["is_user"] = bool(result.data["is_user"])

        return create_success_response(request, response_data)

    except Exception as e:
        logger.error(f"[CloudBaseSendCode] Error: {e}\n{traceback.format_exc()}")
        return create_error_response(request, "SEND_CODE_ERROR", str(e))


# ============================================================
# 校验验证码（获取 verification_token）
# ============================================================

@IPCHandlerRegistry.handler("cloudbase_verify_code")
def handle_cloudbase_verify_code(request: IPCRequest,
                                  params: Optional[Dict[str, Any]]) -> IPCResponse:
    """校验验证码，获取 verification_token（用于后续登录/注册）"""
    try:
        is_valid, data, error = validate_params(params, ["verification_id", "code"])
        if not is_valid:
            return create_error_response(request, "INVALID_PARAMS", error)

        verification_id = data["verification_id"].strip()
        code = data["code"].strip()

        service = _get_service()
        if not service:
            return create_error_response(
                request, "CLOUDBASE_NOT_AVAILABLE",
                auth_messages.get_message("cloudbase_not_available"),
            )

        logger.info(f"[CloudBaseVerifyCode] Verifying code for verification_id")
        result = service.verify_verification_code(verification_id, code)

        if not result.success:
            logger.warning(f"[CloudBaseVerifyCode] Failed: {result.error}")
            return _build_error_response(request, "VERIFY_FAILED",
                                          result, default_key="verification_failed")

        return create_success_response(request, {
            "verification_token": result.data["verification_token"],
            "expires_in": result.data.get("expires_in", 600),
        })

    except Exception as e:
        logger.error(f"[CloudBaseVerifyCode] Error: {e}\n{traceback.format_exc()}")
        return create_error_response(request, "VERIFY_ERROR", str(e))


# ============================================================
# 手机号登录
# ============================================================

@IPCHandlerRegistry.handler("cloudbase_phone_login")
def handle_cloudbase_phone_login(request: IPCRequest,
                                 params: Optional[Dict[str, Any]]) -> IPCResponse:
    """手机号验证码登录（CloudBase 三步流程）

    流程：
    1. cloudbase_send_code → 返回 verification_id
    2. 前端保存 verification_id
    3. 本接口传入 verification_id + 验证码 → 内部完成 verify + sign_in
    """
    lang = auth_messages.DEFAULT_LANG
    try:
        is_valid, data, error = validate_params(params, ["phone", "code"])
        if not is_valid:
            return create_error_response(request, "INVALID_PARAMS", error)

        phone = data["phone"].strip()
        code = data["code"].strip()
        verification_id = data.get("verification_id")
        machine_role = data.get("role", "Commander")
        lang = data.get("lang", auth_messages.DEFAULT_LANG)
        auth_messages.set_language(lang)

        # verification_id 必须传
        if not verification_id:
            logger.warning("[CloudBasePhoneLogin] Missing verification_id")
            return create_error_response(
                request, "INVALID_PARAMS",
                "verification_id is required. Call cloudbase_send_code first.",
            )

        service = _get_service()
        if not service:
            return create_error_response(
                request, "CLOUDBASE_NOT_AVAILABLE",
                auth_messages.get_message("cloudbase_not_available"),
            )

        logger.info(f"[CloudBasePhoneLogin] Phone login for: {phone[:3]}****")

        # Step 1: 验证验证码，获取 verification_token
        verify_result = service.verify_verification_code(verification_id, code)
        if not verify_result.success:
            logger.warning(f"[CloudBasePhoneLogin] Verify failed: {verify_result.error}")
            return _build_error_response(request, "VERIFY_FAILED",
                                          verify_result, default_key="login_failed")

        verification_token = verify_result.data.get("verification_token", "")

        # Step 2: 智能登录 / 注册 (方案 C)
        # CloudBase 的 sign_in / sign_up 是两个独立接口，不能在一个请求里同时完成。
        # 策略：先 sign_in；若返回 NOT_FOUND 则自动 sign_up 给新用户开账号，
        # 用户体感是"输入手机号 + 验证码即可登录"。
        # 边界:已注册但 sign_in 失败 (例如账户被删除) → 自动 provision 新账号，
        # 行为等同用户注销后重新注册，符合预期。
        result = service.sign_in_with_otp(
            phone_number=phone,
            verification_token=verification_token,
        )

        if not result.success and result.error_code == "NOT_FOUND":
            logger.info(
                f"[CloudBasePhoneLogin] Phone {phone[:3]}**** not registered, "
                f"auto-provisioning via sign_up_with_otp"
            )
            result = service.sign_up_with_otp(
                phone_number=phone,
                verification_token=verification_token,
                password="",  # 手机号登录不需要密码,空字符串让 CloudBase 不要求 password
            )

        if not result.success:
            logger.warning(f"[CloudBasePhoneLogin] Failed: {result.error}")
            return _build_error_response(request, "LOGIN_FAILED",
                                          result, default_key="login_failed")

        user_info = CloudBaseUserInfo(**{
            k: v for k, v in result.data["user_info"].items()
            if k in CloudBaseUserInfo.__dataclass_fields__
        })

        return _build_login_response(
            request,
            token=result.data["access_token"],
            refresh_token=result.data["refresh_token"],
            user_info=user_info,
            machine_role=machine_role,
            login_type="phone",
        )

    except Exception as e:
        logger.error(f"[CloudBasePhoneLogin] Error: {e}\n{traceback.format_exc()}")
        auth_messages.set_language(lang)
        return create_error_response(
            request, "LOGIN_ERROR",
            auth_messages.get_message("login_failed"),
        )


# ============================================================
# 登出
# ============================================================

@IPCHandlerRegistry.handler("cloudbase_logout")
def handle_cloudbase_logout(request: IPCRequest,
                            params: Optional[Dict[str, Any]]) -> IPCResponse:
    """CloudBase 登出"""
    try:
        token = params.get("token") if params else None
        service = _get_service()

        if service and token:
            service.sign_out(token)

        return create_success_response(request, {
            "message": auth_messages.get_message("logout_success"),
        })

    except Exception as e:
        logger.error(f"[CloudBaseLogout] Error: {e}")
        return create_success_response(request, {
            "message": "Logout successful",
        })


# ============================================================
# 刷新 Token
# ============================================================

@IPCHandlerRegistry.handler("cloudbase_refresh_token")
def handle_cloudbase_refresh_token(request: IPCRequest,
                                   params: Optional[Dict[str, Any]]) -> IPCResponse:
    """刷新 Token"""
    try:
        refresh_token = params.get("refresh_token") if params else None
        if not refresh_token:
            return create_error_response(
                request, "INVALID_PARAMS", "Refresh token is required"
            )

        service = _get_service()
        if not service:
            return create_error_response(
                request, "CLOUDBASE_NOT_AVAILABLE",
                auth_messages.get_message("cloudbase_not_available"),
            )

        result = service.refresh_token(refresh_token)

        if not result.success:
            return create_error_response(request, "REFRESH_FAILED", result.error)

        return create_success_response(request, {
            "token": result.data["access_token"],
            "refresh_token": result.data["refresh_token"],
        })

    except Exception as e:
        logger.error(f"[CloudBaseRefreshToken] Error: {e}\n{traceback.format_exc()}")
        return create_error_response(request, "REFRESH_ERROR", str(e))


# ============================================================
# 发送密码重置验证码
# ============================================================

@IPCHandlerRegistry.handler("cloudbase_forgot_password")
def handle_cloudbase_forgot_password(request: IPCRequest,
                                      params: Optional[Dict[str, Any]]) -> IPCResponse:
    """发送密码重置验证码"""
    try:
        is_valid, data, error = validate_params(params, ["phone"])
        if not is_valid:
            return create_error_response(request, "INVALID_PARAMS", error)

        phone = data["phone"].strip()
        lang = data.get("lang", auth_messages.DEFAULT_LANG)
        auth_messages.set_language(lang)

        service = _get_service()
        if not service:
            return create_error_response(
                request, "CLOUDBASE_NOT_AVAILABLE",
                auth_messages.get_message("cloudbase_not_available"),
            )

        logger.info(f"[CloudBaseForgotPassword] Sending code to: {phone[:3]}****")
        result = service.send_verification_code(phone_number=phone)

        if not result.success:
            logger.warning(f"[CloudBaseForgotPassword] Failed: {result.error}")
            return _build_error_response(request, "FORGOT_FAILED",
                                          result, default_key="sms_send_failed")

        response_data = {
            "message": auth_messages.get_message("forgot_password_sent"),
        }
        if result.data.get("dev_code"):
            response_data["dev_code"] = result.data["dev_code"]
        # 兼容 CloudBase 两种字段命名（snake_case vs camelCase）
        verification_id = (
            (result.data.get("verification_id") or "")
            or (result.data.get("verificationId") or "")
        )
        if verification_id:
            response_data["verification_id"] = verification_id

        return create_success_response(request, response_data)

    except Exception as e:
        logger.error(f"[CloudBaseForgotPassword] Error: {e}\n{traceback.format_exc()}")
        return create_error_response(request, "FORGOT_ERROR", str(e))


# ============================================================
# 通过手机验证码重置密码
# ============================================================

@IPCHandlerRegistry.handler("cloudbase_reset_password")
def handle_cloudbase_reset_password(request: IPCRequest,
                                     params: Optional[Dict[str, Any]]) -> IPCResponse:
    """通过手机验证码重置密码（CloudBase 三步流程）

    流程：
    1. cloudbase_forgot_password → 返回 verification_id
    2. 前端保存 verification_id
    3. 本接口传入 verification_id + 验证码 → 内部完成 verify + reset
    """
    try:
        is_valid, data, error = validate_params(params, ["phone", "code", "new_password"])
        if not is_valid:
            return create_error_response(request, "INVALID_PARAMS", error)

        phone = data["phone"].strip()
        code = data["code"].strip()
        new_password = data["new_password"]
        verification_id = data.get("verification_id")
        lang = data.get("lang", auth_messages.DEFAULT_LANG)
        auth_messages.set_language(lang)

        # verification_id 必须传
        if not verification_id:
            logger.warning("[CloudBaseResetPassword] Missing verification_id")
            return create_error_response(
                request, "INVALID_PARAMS",
                "verification_id is required. Call cloudbase_forgot_password first.",
            )

        service = _get_service()
        if not service:
            return create_error_response(
                request, "CLOUDBASE_NOT_AVAILABLE",
                auth_messages.get_message("cloudbase_not_available"),
            )

        logger.info(f"[CloudBaseResetPassword] Resetting password for: {phone[:3]}****")
        result = service.reset_password(
            phone_number=phone,
            verification_id=verification_id,
            verification_code=code,
            new_password=new_password,
        )

        if not result.success:
            logger.warning(f"[CloudBaseResetPassword] Failed: {result.error}")
            return _build_error_response(request, "RESET_FAILED",
                                          result, default_key="confirm_forgot_failed")

        return create_success_response(request, {
            "message": auth_messages.get_message("confirm_forgot_success"),
        })

    except Exception as e:
        logger.error(f"[CloudBaseResetPassword] Error: {e}\n{traceback.format_exc()}")
        return create_error_response(
            request, "RESET_ERROR",
            auth_messages.get_message("confirm_forgot_failed"),
        )


# ============================================================
# 手机号注册
# ============================================================

@IPCHandlerRegistry.handler("cloudbase_phone_signup")
def handle_cloudbase_phone_signup(request: IPCRequest,
                                   params: Optional[Dict[str, Any]]) -> IPCResponse:
    """手机号注册（CloudBase 三步流程）

    流程：
    1. cloudbase_send_code → 返回 verification_id
    2. 前端保存 verification_id
    3. 本接口传入 verification_id + 验证码 → 内部完成 verify + signup
    """
    lang = auth_messages.DEFAULT_LANG
    try:
        is_valid, data, error = validate_params(params, ["phone", "code"])
        if not is_valid:
            return create_error_response(request, "INVALID_PARAMS", error)

        phone = data["phone"].strip()
        code = data["code"].strip()
        verification_id = data.get("verification_id")
        password = data.get("password", "")
        machine_role = data.get("role", "Commander")
        lang = data.get("lang", auth_messages.DEFAULT_LANG)
        auth_messages.set_language(lang)

        # verification_id 必须传
        if not verification_id:
            logger.warning("[CloudBasePhoneSignup] Missing verification_id")
            return create_error_response(
                request, "INVALID_PARAMS",
                "verification_id is required. Call cloudbase_send_code first.",
            )

        service = _get_service()
        if not service:
            return create_error_response(
                request, "CLOUDBASE_NOT_AVAILABLE",
                auth_messages.get_message("cloudbase_not_available"),
            )

        logger.info(f"[CloudBasePhoneSignup] Registering: {phone[:3]}****")

        # Step 1: 验证验证码，获取 verification_token
        verify_result = service.verify_verification_code(verification_id, code)
        if not verify_result.success:
            logger.warning(f"[CloudBasePhoneSignup] Verify failed: {verify_result.error}")
            return _build_error_response(request, "VERIFY_FAILED",
                                          verify_result, default_key="signup_failed")

        verification_token = verify_result.data.get("verification_token", "")

        # Step 2: 用 verification_token 完成注册
        result = service.sign_up_with_otp(
            phone_number=phone, verification_token=verification_token, password=password,
        )

        if not result.success:
            logger.warning(f"[CloudBasePhoneSignup] Failed: {result.error}")
            return _build_error_response(request, "SIGNUP_FAILED",
                                          result, default_key="signup_failed")

        user_info = CloudBaseUserInfo(**{
            k: v for k, v in result.data["user_info"].items()
            if k in CloudBaseUserInfo.__dataclass_fields__
        })

        return _build_login_response(
            request,
            token=result.data["access_token"],
            refresh_token=result.data["refresh_token"],
            user_info=user_info,
            machine_role=machine_role,
            login_type="phone",
        )

    except Exception as e:
        logger.error(f"[CloudBasePhoneSignup] Error: {e}\n{traceback.format_exc()}")
        auth_messages.set_language(lang)
        return create_error_response(
            request, "SIGNUP_ERROR",
            auth_messages.get_message("signup_failed"),
        )


# ============================================================
# 微信登录
# ============================================================



# ============================================================
# 检查配置
# ============================================================

@IPCHandlerRegistry.handler("cloudbase_check_config")
def handle_cloudbase_check_config(request: IPCRequest,
                                  params: Optional[Dict[str, Any]]) -> IPCResponse:
    """检查 CloudBase 配置"""
    try:
        if not is_cn():
            return create_success_response(request, {
                "available": False,
                "reason": "CN app only",
                "app_id": get_app_id(),
            })

        service = _get_service()
        if not service:
            return create_success_response(request, {
                "available": False,
                "reason": "Service not available",
            })

        status = service.get_config_status()
        return create_success_response(request, {
            "available": status["configured"],
            "wechat_available": status.get("wechat_configured", False),
            "config": status,
        })

    except Exception as e:
        logger.error(f"[CloudBaseCheckConfig] Error: {e}")
        return create_error_response(request, "CONFIG_ERROR", str(e))


# ============================================================
# 微信扫码登录
# ============================================================



@IPCHandlerRegistry.handler("cloudbase_wechat_h5_login")
def handle_cloudbase_wechat_h5_login(request: IPCRequest,
                                     params: Optional[Dict[str, Any]]) -> IPCResponse:
    """使用 CloudBase 托管登录页进行微信登录

    完整流程（CloudBase 托管模式，无需备案域名、无需本地 OAuth server）：

    1. App 调此接口（state 防 CSRF）
    2. 后端调 CloudBase genProviderRedirectUri：
       - 不传 provider_redirect_uri
       - CloudBase 用自己的备案回调域接收微信回调
    3. 返回微信授权 URL 给前端
    4. 前端跳转到该 URL → 微信扫码授权
    5. 微信回调到 CloudBase 的备案域名
    6. CloudBase 自动处理后，把 code/state 拼到回调 URL
    7. 前端页面加载时，CloudBase SDK detectSessionInUrl 自动捕获
    8. 完成 signInWithProvider 登录
    9. 前端拿 access_token 调 ``cloudbase_finalize_session`` → 后端
       跑完整的登录后续处理（与 Intl 的 password / Google 登录共用同一链路）
    """
    try:
        service = _get_service()
        if not service:
            return create_error_response(
                request, "CLOUDBASE_NOT_AVAILABLE",
                auth_messages.get_message("cloudbase_not_available"),
            )

        state = (params or {}).get("state", f"wechat_{uuid.uuid4().hex[:16]}")

        # 【CloudBase 托管模式】不传 redirect_uri，让 CloudBase 用自己的备案域名作为回调地址
        # 用户扫码授权后，微信回调到 CloudBase 托管页，CloudBase 处理完后通过 URL 参数返回
        result = service.get_wechat_qrcode_link(state=state)

        if not result.success:
            return create_error_response(
                request, "WECHAT_LOGIN_FAILED",
                result.error or "Failed to generate WeChat login URL",
            )

        uri = result.data.get("uri", "")

        return create_success_response(request, {
            "url": uri,
            "state": state,
        })
    except Exception as e:
        logger.error(f"[CloudBaseWechatH5Login] Error: {e}\n{traceback.format_exc()}")
        return create_error_response(request, "WECHAT_LOGIN_ERROR", str(e))


@IPCHandlerRegistry.background_handler("cloudbase_wechat_qr_login")
def handle_cloudbase_wechat_qr_login(request: IPCRequest,
                                     params: Optional[Dict[str, Any]]) -> IPCResponse:
    """桌面 App 微信扫码登录（内嵌浏览器弹窗）。

    复用已验证的 Web 登录链路：在内嵌浏览器弹窗打开已备案域名上的
    ``wechat_login.php``，用户扫码后 PHP 回调完成 code→token 兑换并
    provision CloudBase 用户，把 ``token`` / ``username`` 写入页面
    localStorage。弹窗读到后，本处理器走与邮箱/AWS 登录完全相同的
    ``_build_login_response`` 链路终态化会话（安装 token 到 AuthManager、
    生成 IPC 会话 token、拉起 MainWindow），使桌面拿到与 AWS/Cognito
    登录一致的、用于 API 鉴权的 access token。

    仅桌面模式可用（需要 Qt 主循环打开弹窗）。Web 模式请用
    ``cloudbase_wechat_h5_login``。
    """
    lang = auth_messages.DEFAULT_LANG
    try:
        if os.getenv("ECAN_MODE", "desktop") == "web":
            return create_error_response(
                request, "DESKTOP_ONLY",
                "cloudbase_wechat_qr_login is desktop-only; use cloudbase_wechat_h5_login on web",
            )

        service = _get_service()
        if not service:
            return create_error_response(
                request, "CLOUDBASE_NOT_AVAILABLE",
                auth_messages.get_message("cloudbase_not_available"),
            )

        entry_url = (getattr(service.config, "wechat_login_url", "") or "").strip()
        if not entry_url:
            return create_error_response(
                request, "WECHAT_LOGIN_NOT_CONFIGURED",
                "WeChat login URL is not configured (WECHAT.LOGIN_URL)",
            )

        lang = (params or {}).get("lang", auth_messages.DEFAULT_LANG)

        # Open the dialog on the Qt GUI (qasync) loop and block this IPC
        # thread until the user finishes scanning / cancels.
        import asyncio as _asyncio
        from app_context import AppContext
        loop = AppContext.main_loop
        if not loop or not loop.is_running():
            return create_error_response(
                request, "NO_MAIN_LOOP",
                "Main event loop not running; cannot open WeChat login dialog",
            )

        from gui.auth.wechat_login_dialog import open_wechat_login
        # Scan budget 280s; hard-cap the blocking wait at 310s. The frontend
        # IPC timeout (330s, matching the CIAM wechatLogin precedent) must
        # exceed this so it never aborts before the handler returns.
        timeout_s = 280
        fut = _asyncio.run_coroutine_threadsafe(
            open_wechat_login(entry_url, timeout_s=timeout_s), loop,
        )
        captured = fut.result(timeout=timeout_s + 30)

        if not captured or not captured.get("token"):
            return create_error_response(
                request, "WECHAT_LOGIN_CANCELLED",
                "WeChat login was cancelled or timed out",
            )

        token = captured["token"]
        username = (captured.get("username") or "").strip() or f"wechat_user"

        auth_messages.set_language(lang)
        cb_user_info = CloudBaseUserInfo(
            sub=username,
            username=username,
            email=username if "@" in username else "",
            phone_number="",
            nickname="",
            avatar_url="",
            login_type="wechat",
        )
        return _build_login_response(
            request,
            token=token,
            refresh_token="",
            user_info=cb_user_info,
            machine_role=(params or {}).get("role", "Commander"),
            login_type="wechat",
        )

    except Exception as e:
        logger.error(f"[CloudBaseWechatQRLogin] Error: {e}\n{traceback.format_exc()}")
        auth_messages.set_language(lang)
        return create_error_response(
            request, "WECHAT_LOGIN_ERROR",
            auth_messages.get_message("login_failed"),
        )


# ============================================================
# 微信 / 外部托管登录的会话终态化（让后端接管登录后续处理）
# ============================================================

@IPCHandlerRegistry.handler("cloudbase_finalize_session")
def handle_cloudbase_finalize_session(request: IPCRequest,
                                       params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Finalize a CloudBase session on the backend.

    Used by the WeChat hosted-page flow, where the **frontend** holds the
    access_token (CloudBase's hosted login page returned to it via URL
    fragments / ``detectSessionInUrl``). The frontend has no way to drive
    ``Login.handleLogin`` itself, so it calls this IPC with the token +
    minimal user info to hand control back to the backend.

    Once handed off, the backend runs the same post-login pipeline as
    Intl's password / Google login:

    1. ``AuthManager.complete_login_from_provider`` — install tokens into
       ``self.tokens / signed_in / current_user / user_profile`` and start
       the refresh task.
    2. ``Login.handleLogin`` — schedule ``_async_launch_main_window``
       (or, in web mode, mark ready).
    3. Mint IPC session token + web session (web mode).
    4. Return ``{token, user_info, session_id, message}`` so the frontend
       can finish the redirect to ``/agents``.

    Args:
        access_token:    CloudBase access_token from the callback
        refresh_token:   refresh_token (may be empty)
        expires_in:      TTL in seconds (default 7200)
        user_identifier: email / phone / uuid — preferred key for the session
        user_info:       arbitrary user metadata (avatar, nickname, …)
        role:            machine role (default "Commander")
    """
    lang = auth_messages.DEFAULT_LANG
    try:
        is_valid, data, error = validate_params(params, ["access_token", "user_identifier"])
        if not is_valid:
            return create_error_response(request, "INVALID_PARAMS", error)

        access_token = data["access_token"]
        user_identifier = data["user_identifier"].strip()
        if not user_identifier:
            return create_error_response(
                request, "INVALID_PARAMS", "user_identifier is required",
            )
        refresh_token = data.get("refresh_token") or None
        try:
            expires_in = int(data.get("expires_in", 7200))
        except Exception:
            expires_in = 7200
        machine_role = data.get("role", "Commander")
        lang = data.get("lang", auth_messages.DEFAULT_LANG)
        auth_messages.set_language(lang)

        user_info_raw = data.get("user_info") or {}
        if not isinstance(user_info_raw, dict):
            user_info_raw = {}

        # Build a CloudBaseUserInfo from the frontend's dict so we can reuse
        # the unified _build_login_response path. This guarantees the
        # response shape is identical to a password login.
        cb_user_info = CloudBaseUserInfo(
            sub=str(user_info_raw.get("uuid") or user_info_raw.get("openId") or user_identifier),
            username=user_info_raw.get("username") or user_identifier,
            email=user_info_raw.get("email") or (user_identifier if "@" in user_identifier else ""),
            phone_number=user_info_raw.get("phoneNumber") or (user_identifier if "@" not in user_identifier else ""),
            nickname=user_info_raw.get("nickname") or user_info_raw.get("nickName") or "",
            avatar_url=user_info_raw.get("avatarUrl") or "",
            login_type="wechat",
        )

        return _build_login_response(
            request,
            token=access_token,
            refresh_token=refresh_token or "",
            user_info=cb_user_info,
            machine_role=machine_role,
            login_type="wechat",
        )

    except Exception as e:
        logger.error(f"[CloudBaseFinalizeSession] Error: {e}\n{traceback.format_exc()}")
        auth_messages.set_language(lang)
        return create_error_response(
            request, "FINALIZE_ERROR",
            auth_messages.get_message("login_failed"),
        )
