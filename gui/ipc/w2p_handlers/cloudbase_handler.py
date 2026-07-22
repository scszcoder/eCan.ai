"""
CloudBase Authentication Handler
腾讯云 CloudBase 认证 IPC 处理器

扩展原有的 user_handler，提供 CloudBase 专用的认证功能：
- 手机号 + 验证码登录
- 微信登录
- 邮箱密码登录（通过 CloudBase）

仅在 CN 版本（ECAN_APP_ID=cn）时使用。
"""

import traceback
import json
import os
from typing import Any, Optional, Dict
from dataclasses import asdict

from app_context import AppContext
from gui.ipc.handlers import validate_params
from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import IPCRequest, IPCResponse, create_error_response, create_success_response
from auth.auth_messages import auth_messages
from auth.tencent.cloudbase_auth import CloudBaseAuthService, CloudBaseUserInfo

from utils.logger_helper import logger_helper as logger


def _is_cn_app() -> bool:
    """检查是否为 CN 版本"""
    return os.getenv('ECAN_APP_ID', 'intl') == 'cn'


def _get_cloudbase_service() -> Optional[CloudBaseAuthService]:
    """获取 CloudBase 认证服务实例"""
    if not _is_cn_app():
        return None

    try:
        return CloudBaseAuthService()
    except Exception as e:
        logger.error(f"[CloudBaseHandler] Failed to initialize CloudBase service: {e}")
        return None


# ==================== 错误码映射 ====================

CLOUDBASE_ERROR_MAP = {
    # 登录错误
    'AuthFailure': 'login_invalid_credentials',
    'InvalidParameter': 'login_invalid_credentials',
    'UserNotFound': 'login_invalid_credentials',
    'UserDisabled': 'login_user_disabled',

    # 注册错误
    'UserAlreadyExists': 'signup_user_exists',
    'EmailAlreadyExists': 'signup_user_exists',
    'PhoneAlreadyExists': 'signup_user_exists',
    'WeakPassword': 'signup_invalid_password',

    # 验证码错误
    'InvalidCode': 'confirm_forgot_invalid_code',
    'ExpiredCode': 'confirm_forgot_expired_code',
    'CodeSendFailed': 'forgot_password_failed',
}


def _get_message_from_error(error_code: str, default_key: str) -> str:
    """将 CloudBase 错误码映射到本地化消息"""
    key = CLOUDBASE_ERROR_MAP.get(error_code, default_key)
    return auth_messages.get_message(key)


def _build_user_info_response(request, token: str, user_info: CloudBaseUserInfo,
                              machine_role: str, session_id: Optional[str] = None) -> IPCResponse:
    """构建用户信息响应"""
    response_data = {
        'token': token,
        'message': auth_messages.get_message('login_success'),
        'user_info': {
            'username': user_info.email or user_info.phone_number or user_info.custom_user_id or '',
            'email': user_info.email or '',
            'phone': user_info.phone_number or '',
            'role': machine_role,
            'name': user_info.nickname or '',
            'nickname': user_info.nickname or '',
            'avatar_url': user_info.avatar_url or '',
            'openid': user_info.wx_open_id or '',
            'login_type': user_info.login_type,
            'uuid': user_info.uuid
        }
    }

    if session_id:
        response_data['session_id'] = session_id

    return create_success_response(request, response_data)


# ==================== CloudBase 认证处理器 ====================

@IPCHandlerRegistry.handler('cloudbase_login')
def handle_cloudbase_login(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """
    CloudBase 邮箱密码登录

    请求参数:
        - email: 邮箱地址
        - password: 密码
        - role: 机器角色 (默认 Commander)
    """
    lang = auth_messages.DEFAULT_LANG
    try:
        is_valid, data, error = validate_params(params, ['email', 'password'])
        if not is_valid:
            return create_error_response(request, 'INVALID_PARAMS', error)

        email = data['email']
        password = data['password']
        machine_role = data.get('role', 'Commander')
        lang = data.get('lang', auth_messages.DEFAULT_LANG)
        auth_messages.set_language(lang)

        service = _get_cloudbase_service()
        if not service:
            return create_error_response(request, 'CLOUDBASE_NOT_AVAILABLE',
                                        'CloudBase is only available in CN version')

        logger.info(f"[CloudBaseLogin] Email login for: {email}")

        result = service.sign_in_with_email_and_password(email, password)

        if not result.success:
            error_msg = result.error or 'Login failed'
            message = _get_message_from_error(result.error_code or '', 'login_failed')
            logger.warning(f"[CloudBaseLogin] Failed for {email}: {error_msg}")
            return create_error_response(request, 'CLOUDBASE_LOGIN_ERROR', message)

        # 保存登录信息
        user_info_dict = result.data.get('user_info')
        if isinstance(user_info_dict, CloudBaseUserInfo):
            user_info = user_info_dict
        else:
            user_info = CloudBaseUserInfo(
                uuid=result.data.get('user_info', {}).get('uuid', ''),
                email=email,
                login_type='email'
            )

        token = result.data.get('token', '')

        # 触发 onboarding 检查
        _trigger_onboarding_check()

        return _build_user_info_response(request, token, user_info, machine_role)

    except Exception as e:
        logger.error(f"[CloudBaseLogin] Error: {e} {traceback.format_exc()}")
        auth_messages.set_language(lang)
        return create_error_response(request, 'CLOUDBASE_LOGIN_ERROR',
                                    auth_messages.get_message('login_failed'))


@IPCHandlerRegistry.handler('cloudbase_phone_login')
def handle_cloudbase_phone_login(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """
    CloudBase 手机号验证码登录

    请求参数:
        - phone: 手机号
        - code: 验证码
        - role: 机器角色 (默认 Commander)
    """
    lang = auth_messages.DEFAULT_LANG
    try:
        is_valid, data, error = validate_params(params, ['phone', 'code'])
        if not is_valid:
            return create_error_response(request, 'INVALID_PARAMS', error)

        phone = data['phone']
        code = data['code']
        machine_role = data.get('role', 'Commander')
        lang = data.get('lang', auth_messages.DEFAULT_LANG)
        auth_messages.set_language(lang)

        service = _get_cloudbase_service()
        if not service:
            return create_error_response(request, 'CLOUDBASE_NOT_AVAILABLE',
                                        'CloudBase is only available in CN version')

        logger.info(f"[CloudBasePhoneLogin] Phone login for: {phone}")

        result = service.sign_in_with_phone_number(phone, code)

        if not result.success:
            error_msg = result.error or 'Phone login failed'
            message = _get_message_from_error(result.error_code or '', 'login_failed')
            logger.warning(f"[CloudBasePhoneLogin] Failed for {phone}: {error_msg}")
            return create_error_response(request, 'CLOUDBASE_LOGIN_ERROR', message)

        user_info = result.data.get('user_info')
        if isinstance(user_info, CloudBaseUserInfo):
            user_info.login_type = 'phone'

        token = result.data.get('token', '')

        _trigger_onboarding_check()

        return _build_user_info_response(request, token, user_info, machine_role)

    except Exception as e:
        logger.error(f"[CloudBasePhoneLogin] Error: {e} {traceback.format_exc()}")
        auth_messages.set_language(lang)
        return create_error_response(request, 'CLOUDBASE_LOGIN_ERROR',
                                    auth_messages.get_message('login_failed'))


@IPCHandlerRegistry.handler('cloudbase_send_code')
def handle_cloudbase_send_code(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """
    CloudBase 发送手机验证码

    请求参数:
        - phone: 手机号
        - purpose: 用途 (login, register, reset_password)
    """
    try:
        is_valid, data, error = validate_params(params, ['phone'])
        if not is_valid:
            return create_error_response(request, 'INVALID_PARAMS', error)

        phone = data['phone']
        purpose = data.get('purpose', 'login')

        service = _get_cloudbase_service()
        if not service:
            return create_error_response(request, 'CLOUDBASE_NOT_AVAILABLE',
                                        'CloudBase is only available in CN version')

        logger.info(f"[CloudBaseSendCode] Sending code to: {phone}, purpose: {purpose}")

        result = service.send_phone_verification_code(phone, purpose)

        if not result.success:
            logger.warning(f"[CloudBaseSendCode] Failed for {phone}: {result.error}")
            return create_error_response(request, 'CLOUDBASE_SEND_CODE_ERROR',
                                        result.error or 'Failed to send code')

        return create_success_response(request, {
            'message': auth_messages.get_message('forgot_password_sent')
        })

    except Exception as e:
        logger.error(f"[CloudBaseSendCode] Error: {e} {traceback.format_exc()}")
        return create_error_response(request, 'CLOUDBASE_SEND_CODE_ERROR', str(e))


@IPCHandlerRegistry.handler('cloudbase_wechat_login')
def handle_cloudbase_wechat_login(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """
    CloudBase 微信登录

    请求参数:
        - code: 微信授权码
        - role: 机器角色 (默认 Commander)
    """
    lang = auth_messages.DEFAULT_LANG
    try:
        is_valid, data, error = validate_params(params, ['code'])
        if not is_valid:
            return create_error_response(request, 'INVALID_PARAMS', error)

        code = data['code']
        machine_role = data.get('role', 'Commander')
        lang = data.get('lang', auth_messages.DEFAULT_LANG)
        auth_messages.set_language(lang)

        service = _get_cloudbase_service()
        if not service:
            return create_error_response(request, 'CLOUDBASE_NOT_AVAILABLE',
                                        'CloudBase is only available in CN version')

        logger.info(f"[CloudBaseWechatLogin] WeChat login with code: {code[:20]}...")

        result = service.sign_in_with_wechat(code)

        if not result.success:
            error_msg = result.error or 'WeChat login failed'
            message = _get_message_from_error(result.error_code or '', 'login_failed')
            logger.warning(f"[CloudBaseWechatLogin] Failed: {error_msg}")
            return create_error_response(request, 'CLOUDBASE_WECHAT_ERROR', message)

        user_info = result.data.get('user_info')
        if isinstance(user_info, CloudBaseUserInfo):
            user_info.login_type = 'wechat'

        token = result.data.get('token', '')

        _trigger_onboarding_check()

        return _build_user_info_response(request, token, user_info, machine_role)

    except Exception as e:
        logger.error(f"[CloudBaseWechatLogin] Error: {e} {traceback.format_exc()}")
        auth_messages.set_language(lang)
        return create_error_response(request, 'CLOUDBASE_WECHAT_ERROR',
                                    auth_messages.get_message('login_failed'))


@IPCHandlerRegistry.handler('cloudbase_signup')
def handle_cloudbase_signup(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """
    CloudBase 邮箱注册

    请求参数:
        - email: 邮箱地址
        - password: 密码
    """
    lang = auth_messages.DEFAULT_LANG
    try:
        is_valid, data, error = validate_params(params, ['email', 'password'])
        if not is_valid:
            return create_error_response(request, 'INVALID_PARAMS', error)

        email = data['email']
        password = data['password']
        lang = data.get('lang', auth_messages.DEFAULT_LANG)
        auth_messages.set_language(lang)

        service = _get_cloudbase_service()
        if not service:
            return create_error_response(request, 'CLOUDBASE_NOT_AVAILABLE',
                                        'CloudBase is only available in CN version')

        logger.info(f"[CloudBaseSignup] Registering: {email}")

        result = service.sign_up_with_email_and_password(email, password)

        if not result.success:
            error_msg = result.error or 'Signup failed'
            message = _get_message_from_error(result.error_code or '', 'signup_failed')
            logger.warning(f"[CloudBaseSignup] Failed for {email}: {error_msg}")
            return create_error_response(request, 'CLOUDBASE_SIGNUP_ERROR', message)

        return create_success_response(request, {
            'message': auth_messages.get_message('signup_success')
        })

    except Exception as e:
        logger.error(f"[CloudBaseSignup] Error: {e} {traceback.format_exc()}")
        auth_messages.set_language(lang)
        return create_error_response(request, 'CLOUDBASE_SIGNUP_ERROR',
                                    auth_messages.get_message('signup_failed'))


@IPCHandlerRegistry.handler('cloudbase_get_user_info')
def handle_cloudbase_get_user_info(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """
    CloudBase 获取用户信息

    请求参数:
        - token: 刷新令牌
    """
    try:
        token = params.get('token') if params else None
        if not token:
            return create_error_response(request, 'INVALID_PARAMS', 'Token is required')

        service = _get_cloudbase_service()
        if not service:
            return create_error_response(request, 'CLOUDBASE_NOT_AVAILABLE',
                                        'CloudBase is only available in CN version')

        result = service.get_user_info(token)

        if not result.success:
            return create_error_response(request, 'CLOUDBASE_GET_USER_ERROR', result.error)

        user_info = result.data.get('user_info')

        return create_success_response(request, {
            'user_info': asdict(user_info) if isinstance(user_info, CloudBaseUserInfo) else user_info
        })

    except Exception as e:
        logger.error(f"[CloudBaseGetUserInfo] Error: {e} {traceback.format_exc()}")
        return create_error_response(request, 'CLOUDBASE_GET_USER_ERROR', str(e))


@IPCHandlerRegistry.handler('cloudbase_logout')
def handle_cloudbase_logout(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """
    CloudBase 用户登出

    请求参数:
        - token: 刷新令牌
    """
    lang = auth_messages.DEFAULT_LANG
    try:
        token = params.get('token') if params else None
        if not token:
            return create_error_response(request, 'INVALID_PARAMS', 'Token is required')

        service = _get_cloudbase_service()
        if not service:
            return create_error_response(request, 'CLOUDBASE_NOT_AVAILABLE',
                                        'CloudBase is only available in CN version')

        result = service.sign_out(token)

        if not result.success:
            logger.warning(f"[CloudBaseLogout] Failed: {result.error}")

        return create_success_response(request, {
            'message': auth_messages.get_message('logout_success')
        })

    except Exception as e:
        logger.error(f"[CloudBaseLogout] Error: {e} {traceback.format_exc()}")
        auth_messages.set_language(lang)
        return create_error_response(request, 'CLOUDBASE_LOGOUT_ERROR',
                                    auth_messages.get_message('logout_failed'))


@IPCHandlerRegistry.handler('cloudbase_refresh_token')
def handle_cloudbase_refresh_token(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """
    CloudBase 刷新令牌

    请求参数:
        - refresh_token: 刷新令牌
    """
    try:
        refresh_token = params.get('refresh_token') if params else None
        if not refresh_token:
            return create_error_response(request, 'INVALID_PARAMS', 'Refresh token is required')

        service = _get_cloudbase_service()
        if not service:
            return create_error_response(request, 'CLOUDBASE_NOT_AVAILABLE',
                                        'CloudBase is only available in CN version')

        result = service.refresh_token(refresh_token)

        if not result.success:
            return create_error_response(request, 'CLOUDBASE_REFRESH_ERROR', result.error)

        return create_success_response(request, {
            'token': result.data.get('token'),
            'refresh_token': result.data.get('refresh_token')
        })

    except Exception as e:
        logger.error(f"[CloudBaseRefreshToken] Error: {e} {traceback.format_exc()}")
        return create_error_response(request, 'CLOUDBASE_REFRESH_ERROR', str(e))


@IPCHandlerRegistry.handler('cloudbase_check_config')
def handle_cloudbase_check_config(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """
    检查 CloudBase 配置是否正确

    返回:
        - available: 是否可用
        - config: 配置信息
    """
    try:
        service = _get_cloudbase_service()

        if not service:
            return create_success_response(request, {
                'available': False,
                'reason': 'CloudBase is only available in CN version',
                'app_id': os.getenv('ECAN_APP_ID', 'intl')
            })

        # 检查配置
        config = service._config
        has_env_id = bool(config.get('env_id'))
        has_credentials = bool(config.get('secret_id') and config.get('secret_key'))

        return create_success_response(request, {
            'available': has_env_id and has_credentials,
            'reason': None if (has_env_id and has_credentials) else 'Missing credentials',
            'has_env_id': has_env_id,
            'has_credentials': has_credentials,
            'region': config.get('region', 'ap-guangzhou'),
            'wechat_enabled': config.get('wechat_enabled', False)
        })

    except Exception as e:
        logger.error(f"[CloudBaseCheckConfig] Error: {e} {traceback.format_exc()}")
        return create_error_response(request, 'CLOUDBASE_CONFIG_ERROR', str(e))


# ==================== 辅助函数 ====================

def _trigger_onboarding_check():
    """触发 onboarding 检查"""
    try:
        config_manager = AppContext.get_config_manager()
        if config_manager and hasattr(config_manager, 'llm_manager'):
            config_manager.llm_manager.reset_onboarding_flag()

            import asyncio
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(config_manager.llm_manager.check_and_show_onboarding(
                    delay_seconds=3.0,
                    force_check=False
                ))
                logger.debug("[CloudBaseHandler] Scheduled onboarding check")
            except RuntimeError:
                logger.debug("[CloudBaseHandler] No event loop available for onboarding check")
    except Exception as e:
        logger.debug(f"[CloudBaseHandler] Could not schedule onboarding check: {e}")
