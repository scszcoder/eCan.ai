import traceback
from typing import Any, Optional, Dict
import uuid
from app_context import AppContext
from gui.LoginoutGUI import Login
from gui.ipc.handlers import validate_params
from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import IPCRequest, IPCResponse, create_error_response, create_success_response

from utils.logger_helper import logger_helper as logger

@IPCHandlerRegistry.handler('login')
def handle_login(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """处理登录请求
    
    验证用户凭据并返回访问令牌。
    
    Args:
        request: IPC 请求对象
        params: 请求参数，必须包含 'username' 和 'password' 字段
        
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
        
        # 获取用户名和密码
        username = data['username']
        password = data['password']
        machine_role = data['machine_role']
        logger.debug("user name:" + username + " password:" + password + " machine_role:" + machine_role)
        
        ctx = AppContext()
        login: Login = ctx.login
        result = login.handleLogin(username, password, machine_role)
        # 简单的密码验证
        if result == 'Successful':
            # 生成随机令牌
            token = str(uuid.uuid4()).replace('-', '')
            logger.info(f"Login successful for user: {username}")
            return create_success_response(request, {
                'token': token,
                'message': 'Login successful'
            })
        else:
            logger.warning(f"Invalid password for user: {username}")
            return create_error_response(
                request,
                'INVALID_CREDENTIALS',
                'Invalid username or password'
            )
    except Exception as e:
        logger.error(f"Error in login handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during login: {str(e)}"
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