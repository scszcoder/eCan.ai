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
            "uuid": user_info.uuid,
            "username": user_info.email or user_info.phone_number or user_info.uuid,
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
    """CloudBase 邮箱注册"""
    lang = auth_messages.DEFAULT_LANG
    try:
        is_valid, data, error = validate_params(params, ["email", "password"])
        if not is_valid:
            return create_error_response(request, "INVALID_PARAMS", error)

        email = data["email"].strip().lower()
        password = data["password"]
        lang = data.get("lang", auth_messages.DEFAULT_LANG)
        auth_messages.set_language(lang)

        service = _get_service()
        if not service:
            return create_error_response(
                request, "CLOUDBASE_NOT_AVAILABLE",
                auth_messages.get_message("cloudbase_not_available"),
            )

        logger.info(f"[CloudBaseSignup] Registering: {email}")
        result = service.sign_up_with_email(email, password)

        if not result.success:
            message = _localized_error(result.error_code, "signup_failed")
            logger.warning(f"[CloudBaseSignup] Failed: {result.error}")
            return create_error_response(request, "SIGNUP_FAILED", message)

        return create_success_response(request, {
            "message": result.data.get("message") or auth_messages.get_message("signup_success"),
        })

    except Exception as e:
        logger.error(f"[CloudBaseSignup] Error: {e}\n{traceback.format_exc()}")
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
        result = service.sign_in_with_email(email, password)

        if not result.success:
            if result.error_code == "NOT_CONFIGURED":
                return create_error_response(
                    request, "CLOUDBASE_NOT_AVAILABLE",
                    auth_messages.get_message("cloudbase_not_available"),
                )
            message = _localized_error(result.error_code, "login_failed")
            logger.warning(f"[CloudBaseLogin] Failed for {email}: {result.error}")
            return create_error_response(request, "LOGIN_FAILED", message)

        user_info = CloudBaseUserInfo(**{
            k: v for k, v in result.data["user_info"].items()
            if k in CloudBaseUserInfo.__dataclass_fields__
        })

        return _build_login_response(
            request,
            token=result.data["token"],
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


# ============================================================
# 发送手机验证码
# ============================================================

@IPCHandlerRegistry.handler("cloudbase_send_code")
def handle_cloudbase_send_code(request: IPCRequest,
                               params: Optional[Dict[str, Any]]) -> IPCResponse:
    """发送手机验证码"""
    try:
        is_valid, data, error = validate_params(params, ["phone"])
        if not is_valid:
            return create_error_response(request, "INVALID_PARAMS", error)

        phone = data["phone"].strip()
        purpose = data.get("purpose", "login")
        lang = data.get("lang", auth_messages.DEFAULT_LANG)
        auth_messages.set_language(lang)

        service = _get_service()
        if not service:
            return create_error_response(
                request, "CLOUDBASE_NOT_AVAILABLE",
                auth_messages.get_message("cloudbase_not_available"),
            )

        logger.info(f"[CloudBaseSendCode] Sending code to: {phone[:3]}****, purpose: {purpose}")
        result = service.send_phone_verification_code(phone, purpose)

        if not result.success:
            message = _localized_error(result.error_code, "sms_send_failed")
            logger.warning(f"[CloudBaseSendCode] Failed: {result.error}")
            return create_error_response(request, "SEND_CODE_FAILED", message)

        response_data = {
            "message": auth_messages.get_message("code_sent"),
        }
        # 开发模式：返回验证码便于测试
        if result.data.get("dev_code"):
            response_data["dev_code"] = result.data["dev_code"]

        return create_success_response(request, response_data)

    except Exception as e:
        logger.error(f"[CloudBaseSendCode] Error: {e}\n{traceback.format_exc()}")
        return create_error_response(request, "SEND_CODE_ERROR", str(e))


# ============================================================
# 手机号登录
# ============================================================

@IPCHandlerRegistry.handler("cloudbase_phone_login")
def handle_cloudbase_phone_login(request: IPCRequest,
                                 params: Optional[Dict[str, Any]]) -> IPCResponse:
    """手机号验证码登录"""
    lang = auth_messages.DEFAULT_LANG
    try:
        is_valid, data, error = validate_params(params, ["phone", "code"])
        if not is_valid:
            return create_error_response(request, "INVALID_PARAMS", error)

        phone = data["phone"].strip()
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

        logger.info(f"[CloudBasePhoneLogin] Phone login for: {phone[:3]}****")
        result = service.sign_in_with_phone(phone, code)

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
            token=result.data["token"],
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
            "token": result.data["token"],
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
        result = service.forgot_password_with_phone(phone)

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
        result = service.reset_password_with_phone(phone, code, new_password)

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
        result = service.sign_up_with_phone(phone, code, password)

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
            token=result.data["token"],
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
            token=result.data["token"],
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
