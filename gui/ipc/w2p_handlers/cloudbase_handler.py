"""
CloudBase Authentication IPC Handler
腾讯云 CloudBase 认证 IPC 处理器

仅在 CN 版本（ECAN_APP_ID=cn）时可用。
"""

import os
import traceback
from typing import Any, Dict, Optional

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


def _is_cn_app() -> bool:
    """检查是否为 CN 版本"""
    return os.getenv("ECAN_APP_ID", "intl") == "cn"


def _get_service():
    """获取 CloudBase 服务"""
    if not _is_cn_app():
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


def _build_login_response(request: IPCRequest, token: str,
                          refresh_token: str,
                          user_info: CloudBaseUserInfo,
                          machine_role: str = "Commander") -> IPCResponse:
    """构建登录成功响应"""
    return create_success_response(request, {
        "token": token,
        "refresh_token": refresh_token,
        "message": auth_messages.get_message("login_success"),
        "user_info": {
            "uuid": user_info.sub,
            "username": user_info.email or user_info.phone_number or user_info.sub,
            "email": user_info.email or "",
            "phone": user_info.phone_number or "",
            "nickname": user_info.nickname or "",
            "avatar_url": user_info.avatar_url or "",
            "role": machine_role,
            "login_type": user_info.login_type,
        },
    })


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
        username = data.get("username", "").strip() or email.split("@")[0]
        lang = data.get("lang", auth_messages.DEFAULT_LANG)
        auth_messages.set_language(lang)

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
            message = _localized_error(send_result.error_code, "signup_failed")
            return create_error_response(request, "SEND_CODE_FAILED", message)

        is_user = send_result.data.get("is_user")
        if is_user:
            return create_error_response(
                request, "USER_EXISTS",
                "This email is already registered. Please log in instead.",
            )

        verification_id = send_result.data.get("verification_id", "")

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
        username = data.get("username", "").strip() or email.split("@")[0]
        lang = data.get("lang", auth_messages.DEFAULT_LANG)
        auth_messages.set_language(lang)

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
            message = _localized_error(verify_result.error_code, "signup_failed")
            return create_error_response(request, "VERIFY_FAILED", message)

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
            message = _localized_error(signup_result.error_code, "signup_failed")
            logger.warning(f"[CloudBaseSignupConfirm] Failed: {signup_result.error}")
            return create_error_response(request, "SIGNUP_FAILED", message)

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

        logger.info(f"[CloudBaseLogin] Email login for: {email}")
        result = service.sign_in_with_password(email, password)

        if not result.success:
            if result.error_code == "NOT_CONFIGURED":
                return create_error_response(
                    request, "CLOUDBASE_NOT_AVAILABLE",
                    auth_messages.get_message("cloudbase_not_available"),
                )
            message = _localized_error(result.error_code, "login_failed")
            logger.warning(f"[CloudBaseLogin] Failed for {email}: {result.error}")
            return create_error_response(request, "LOGIN_FAILED", message)

        # /auth/v1/signin 响应不含 email，先用初始 user_info
        user_info = CloudBaseUserInfo(**{
            k: v for k, v in result.data["user_info"].items()
            if k in CloudBaseUserInfo.__dataclass_fields__
        })

        # 补全：调 /auth/v1/user/me 获取完整用户信息（含 email、username 等）
        me = service.get_current_user(result.data["access_token"])
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

        # 保存密码和 refresh_token 到 keyring，下次启动自动恢复会话
        _save_cloudbase_credentials(email, password, machine_role,
                                 refresh_token=result.data.get("refresh_token"))

        return _build_login_response(
            request,
            token=result.data["access_token"],
            refresh_token=result.data["refresh_token"],
            user_info=user_info,
            machine_role=machine_role,
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
            message = _localized_error(result.error_code, "sms_send_failed")
            logger.warning(f"[CloudBaseSendCode] Failed: {result.error}")
            return create_error_response(request, "SEND_CODE_FAILED", message)

        response_data: Dict[str, Any] = {
            "message": auth_messages.get_message("code_sent"),
            "type": "phone" if phone else "email",
        }
        # 开发模式：返回验证码便于测试
        if result.data and result.data.get("dev_code"):
            response_data["dev_code"] = result.data["dev_code"]
        # 邮箱模式返回 verification_id（后续需用户输入验证码来换 token）
        if result.data and result.data.get("verification_id"):
            response_data["verification_id"] = result.data["verification_id"]

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
            message = _localized_error(result.error_code, "verification_failed")
            logger.warning(f"[CloudBaseVerifyCode] Failed: {result.error}")
            return create_error_response(request, "VERIFY_FAILED", message)

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
    """手机号验证码登录

    CloudBase 要求两步:
    1. cloudbase_send_code → 返回 verification_id
    2. 本接口 → 传入 verification_id + 用户收到的验证码 → 完成登录
    """
    lang = auth_messages.DEFAULT_LANG
    try:
        is_valid, data, error = validate_params(params, ["phone", "code"])
        if not is_valid:
            return create_error_response(request, "INVALID_PARAMS", error)

        phone = data["phone"].strip()
        code = data["code"].strip()
        verification_id = data.get("verification_id", "").strip() or None
        machine_role = data.get("role", "Commander")
        lang = data.get("lang", auth_messages.DEFAULT_LANG)
        auth_messages.set_language(lang)

        service = _get_service()
        if not service:
            return create_error_response(
                request, "CLOUDBASE_NOT_AVAILABLE",
                auth_messages.get_message("cloudbase_not_available"),
            )

        logger.info(f"[CloudBasePhoneLogin] Phone login for: {phone[:3]}****")

        # Step 1: 如果有 verification_id,说明是两步流程,先验证获取 token
        verification_token = code
        if verification_id:
            verify_result = service.verify_verification_code(verification_id, code)
            if not verify_result.success:
                message = _localized_error(verify_result.error_code, "login_failed")
                logger.warning(f"[CloudBasePhoneLogin] Verify failed: {verify_result.error}")
                return create_error_response(request, "VERIFY_FAILED", message)
            verification_token = verify_result.data.get("verification_token", "")

        # Step 2: 用 verification_token 完成登录
        result = service.sign_in_with_otp(
            phone_number=phone,
            verification_token=verification_token,
        )

        if not result.success:
            message = _localized_error(result.error_code, "login_failed")
            logger.warning(f"[CloudBasePhoneLogin] Failed: {result.error}")
            return create_error_response(request, "LOGIN_FAILED", message)

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
            message = _localized_error(result.error_code, "sms_send_failed")
            logger.warning(f"[CloudBaseForgotPassword] Failed: {result.error}")
            return create_error_response(request, "FORGOT_FAILED", message)

        response_data = {
            "message": auth_messages.get_message("forgot_password_sent"),
        }
        if result.data.get("dev_code"):
            response_data["dev_code"] = result.data["dev_code"]

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
    """通过手机验证码重置密码"""
    try:
        is_valid, data, error = validate_params(params, ["phone", "code", "new_password"])
        if not is_valid:
            return create_error_response(request, "INVALID_PARAMS", error)

        phone = data["phone"].strip()
        code = data["code"].strip()
        new_password = data["new_password"]
        lang = data.get("lang", auth_messages.DEFAULT_LANG)
        auth_messages.set_language(lang)

        service = _get_service()
        if not service:
            return create_error_response(
                request, "CLOUDBASE_NOT_AVAILABLE",
                auth_messages.get_message("cloudbase_not_available"),
            )

        logger.info(f"[CloudBaseResetPassword] Resetting password for: {phone[:3]}****")
        result = service.reset_password(
            phone_number=phone, code=code, new_password=new_password,
        )

        if not result.success:
            message = _localized_error(result.error_code, "confirm_forgot_failed")
            logger.warning(f"[CloudBaseResetPassword] Failed: {result.error}")
            return create_error_response(request, "RESET_FAILED", message)

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
    """手机号注册"""
    lang = auth_messages.DEFAULT_LANG
    try:
        is_valid, data, error = validate_params(params, ["phone", "code"])
        if not is_valid:
            return create_error_response(request, "INVALID_PARAMS", error)

        phone = data["phone"].strip()
        code = data["code"].strip()
        password = data.get("password", "")
        machine_role = data.get("role", "Commander")
        lang = data.get("lang", auth_messages.DEFAULT_LANG)
        auth_messages.set_language(lang)

        service = _get_service()
        if not service:
            return create_error_response(
                request, "CLOUDBASE_NOT_AVAILABLE",
                auth_messages.get_message("cloudbase_not_available"),
            )

        logger.info(f"[CloudBasePhoneSignup] Registering: {phone[:3]}****")
        result = service.sign_up_with_otp(
            phone_number=phone, verification_token=code, password=password,
        )

        if not result.success:
            message = _localized_error(result.error_code, "signup_failed")
            logger.warning(f"[CloudBasePhoneSignup] Failed: {result.error}")
            return create_error_response(request, "SIGNUP_FAILED", message)

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

@IPCHandlerRegistry.handler("cloudbase_wechat_login")
def handle_cloudbase_wechat_login(request: IPCRequest,
                                   params: Optional[Dict[str, Any]]) -> IPCResponse:
    """微信 OAuth 登录"""
    try:
        is_valid, data, error = validate_params(params, ["code"])
        if not is_valid:
            return create_error_response(request, "INVALID_PARAMS", error)

        code = data["code"].strip()
        machine_role = data.get("role", "Commander")
        lang = data.get("lang", auth_messages.DEFAULT_LANG)
        auth_messages.set_language(lang)

        service = _get_service()
        if not service:
            return create_error_response(
                request, "CLOUDBASE_NOT_AVAILABLE",
                auth_messages.get_message("cloudbase_not_available"),
            )

        logger.info("[CloudBaseWechatLogin] Logging in via WeChat")
        result = service.login_with_wechat(code)

        if not result.success:
            logger.warning(f"[CloudBaseWechatLogin] Failed: {result.error}")
            return create_error_response(
                request, "LOGIN_FAILED",
                result.error or "WeChat login failed",
            )

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
        )

    except Exception as e:
        logger.error(f"[CloudBaseWechatLogin] Error: {e}\n{traceback.format_exc()}")
        return create_error_response(request, "LOGIN_ERROR", str(e))


# ============================================================
# 检查配置
# ============================================================

@IPCHandlerRegistry.handler("cloudbase_check_config")
def handle_cloudbase_check_config(request: IPCRequest,
                                  params: Optional[Dict[str, Any]]) -> IPCResponse:
    """检查 CloudBase 配置"""
    try:
        if not _is_cn_app():
            return create_success_response(request, {
                "available": False,
                "reason": "CN app only",
                "app_id": os.getenv("ECAN_APP_ID", "intl"),
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
            "config": status,
        })

    except Exception as e:
        logger.error(f"[CloudBaseCheckConfig] Error: {e}")
        return create_error_response(request, "CONFIG_ERROR", str(e))
