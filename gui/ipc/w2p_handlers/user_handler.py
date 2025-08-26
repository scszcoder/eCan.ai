import traceback
from typing import Any, Optional, Dict
import uuid
from app_context import AppContext
from gui.LoginoutGUI import Login
from gui.ipc.handlers import validate_params
from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import IPCRequest, IPCResponse, create_error_response, create_success_response
from auth.auth_messages import auth_messages

from utils.logger_helper import logger_helper as logger

@IPCHandlerRegistry.handler('login')
def handle_login(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """处理登录请求
    
    验证用户凭据并返回访问令牌。
    
    Args:
        request: IPC 请求对象
        params: 请求参数，必须包含 'username' 和 'password' 字段，可选 'lang' 字段
        
    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"Login handler called with request: {request}")
        
        # 验证参数
        is_valid, data, error = validate_params(params, ['username', 'password'])
        if not is_valid:
            logger.warning(f"Invalid parameters for login: {error}")
            return create_error_response(
                request,
                'INVALID_PARAMS',
                error
            )
        
        # 获取用户名、密码和语言参数
        username = data['username']
        password = data['password']
        machine_role = data.get('machine_role', 'Commander')
        lang = data.get('lang', auth_messages.DEFAULT_LANG)  # 如果为空使用系统默认语言
        
        # 设置国际化语言
        auth_messages.set_language(lang)
        
        logger.debug(f"user name: {username}, password: [HIDDEN], machine_role: {machine_role}, lang: {lang}")
        
        ctx = AppContext()
        login: Login = ctx.login
        result = login.handleLogin(username, password, machine_role)
        
        # 处理不同的登录结果
        if result == 'Successful':
            # 生成随机令牌
            token = str(uuid.uuid4()).replace('-', '')
            logger.info(f"Login successful for user: {username}")
            return create_success_response(request, {
                'token': token,
                'message': auth_messages.get_message('login_success')
            })
        elif result == 'NetworkError':
            logger.error(f"Network error during login for user: {username}")
            return create_error_response(
                request,
                'NETWORK_ERROR',
                auth_messages.get_message('login_network_error')
            )
        elif result == 'TimeoutError':
            logger.error(f"Authentication timeout for user: {username}")
            return create_error_response(
                request,
                'TIMEOUT_ERROR',
                auth_messages.get_message('login_timeout_error')
            )
        else:
            logger.warning(f"Invalid credentials for user: {username}")
            return create_error_response(
                request,
                'INVALID_CREDENTIALS',
                auth_messages.get_message('login_invalid_credentials')
            )
    except Exception as e:
        logger.error(f"Error in login handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'LOGIN_ERROR',
            auth_messages.get_message('login_failed')
        )

@IPCHandlerRegistry.handler('get_last_login')
def handle_get_last_login(request: IPCRequest, params: Optional[Any]) -> IPCResponse:
    """处理获取最后一次登录信息的请求

    Args:
        request: IPC 请求对象
        params: 请求参数 (未使用)

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"Get Last Login handler called with request: {request}")

        ctx = AppContext()
        login: Login = ctx.login
        result = login.handleGetLastLogin()

        logger.info(f"Get Last Login Info successful.")
        return create_success_response(request, {
            'last_login': result,
            'message': 'Get Last Login successful'
        })

    except Exception as e:
        logger.error(f"Error in get_last_login handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during get_last_login: {str(e)}"
        )
    
@IPCHandlerRegistry.handler('logout')
def handle_logout(request: IPCRequest, params: Optional[Any]) -> IPCResponse:
    """处理获取最后一次登录信息的请求

    Args:
        request: IPC 请求对象
        params: 请求参数 (未使用)

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"Logout handler called with request: {request}")

        ctx = AppContext()
        login: Login = ctx.login
        result = login.handleLogout()

        logger.info(f"Logout successful.")
        return create_success_response(request, {
            "result": result,
            'message': 'Logout successful'
        })

    except Exception as e:
        logger.error(f"Error in logout handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'LOGOUT_ERROR',
            f"Error during logout: {str(e)}"
        )

@IPCHandlerRegistry.handler('signup')
def handle_signup(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """处理注册请求
    Args:
        request: IPC 请求对象
        params: 请求参数，必须包含 'username' 和 'password' 字段，可选 'lang' 字段
    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"SignUp handler called with request: {request}")
        is_valid, data, error = validate_params(params, ['username', 'password'])
        if not is_valid:
            logger.warning(f"Invalid parameters for signup: {error}")
            return create_error_response(
                request,
                'INVALID_PARAMS',
                error
            )
        username = data['username']
        password = data['password']
        lang = data.get('lang', auth_messages.DEFAULT_LANG)  # 如果为空使用系统默认语言
        
        # 设置国际化语言
        auth_messages.set_language(lang)
        ctx = AppContext()
        login: Login = ctx.login
        success, message = login.handleSignUp(username, password)
        if success == True:
            logger.info(f"SignUp successful for user: {username}")
            return create_success_response(request, {
                'message': message
            })
        else:
            logger.warning(f"SignUp failed for user: {username}")
            return create_error_response(
                request,
                'SIGNUP_FAILED',
                message
            )
    except Exception as e:
        logger.error(f"Error in signup handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'SIGNUP_ERROR',
            f"Error during signup: {str(e)}"
        )

@IPCHandlerRegistry.handler('forgot_password')
def handle_forgot_password(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """处理忘记密码请求
    Args:
        request: IPC 请求对象
        params: 请求参数，必须包含 'username' 字段，可选 'lang' 字段
    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"ForgotPassword handler called with request: {request}")
        is_valid, data, error = validate_params(params, ['username'])
        if not is_valid:
            logger.warning(f"Invalid parameters for forgot_password: {error}")
            return create_error_response(
                request,
                'INVALID_PARAMS',
                error
            )
        username = data['username']
        lang = data.get('lang', auth_messages.DEFAULT_LANG)  # 如果为空使用系统默认语言
        
        # 设置国际化语言
        auth_messages.set_language(lang)
        ctx = AppContext()
        login: Login = ctx.login
        success = login.handleForgotPassword(username)
        logger.info(f"ForgotPassword process started for user: {username}")
        if success == True:
            return create_success_response(request, {
                'message': auth_messages.get_message('forgot_password_sent')
            })
        else:
            return create_error_response(
                request,
                'FORGOT_PASSWORD_ERROR',
                auth_messages.get_message('forgot_password_failed')
            )
    except Exception as e:
        logger.error(f"Error in forgot_password handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'FORGOT_PASSWORD_ERROR',
            auth_messages.get_message('forgot_password_failed')
        )

@IPCHandlerRegistry.handler('confirm_forgot_password')
def handle_confirm_forgot_password(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """处理确认忘记密码请求
    Args:
        request: IPC 请求对象
        params: 请求参数，必须包含 'username', 'confirmCode', 'newPassword' 字段，可选 'lang' 字段
    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"ConfirmForgotPassword handler called with request: {request}")
        is_valid, data, error = validate_params(params, ['username', 'confirmCode', 'newPassword'])
        if not is_valid:
            logger.warning(f"Invalid parameters for confirm_forgot_password: {error}")
            return create_error_response(
                request,
                'INVALID_PARAMS',
                error
            )
        username = data['username']
        confirm_code = data['confirmCode']
        new_password = data['newPassword']
        lang = data.get('lang', auth_messages.DEFAULT_LANG)  # 如果为空使用系统默认语言
        
        # 设置国际化语言
        auth_messages.set_language(lang)
        
        ctx = AppContext()
        login: Login = ctx.login

        success, message = login.handleConfirmForgotPassword(username, confirm_code, new_password)
        if success:
            logger.info(f"ConfirmForgotPassword successful for user: {username}")
            return create_success_response(request, {
                'message': auth_messages.get_message('confirm_forgot_success')
            })
        else:
            logger.warning(f"ConfirmForgotPassword failed for user: {username}, error: {message}")
            return create_error_response(
                request,
                'CONFIRM_FORGOT_PASSWORD_FAILED',
                message
            )
    except Exception as e:
        logger.error(f"Error in confirm_forgot_password handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'CONFIRM_FORGOT_PASSWORD_ERROR',
            auth_messages.get_message('confirm_forgot_failed')
        )