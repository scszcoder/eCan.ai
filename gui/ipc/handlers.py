"""
IPC 处理器实现模块
提供各种 IPC 请求的具体处理实现
"""

from typing import Any, Optional, Dict
from .types import IPCRequest, create_success_response, create_error_response
from .registry import IPCHandlerRegistry
from utils.logger_helper import logger_helper
import json
import uuid

logger = logger_helper.logger

def validate_params(params: Optional[Dict[str, Any]], required: list[str]) -> tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
    """验证请求参数
    
    Args:
        params: 请求参数
        required: 必需参数列表
        
    Returns:
        tuple[bool, Optional[Dict[str, Any]], Optional[str]]: (是否有效, 参数数据, 错误信息)
    """
    if not params:
        return False, None, f"Missing required parameters: {', '.join(required)}"
    
    missing = [param for param in required if param not in params]
    if missing:
        return False, None, f"Missing required parameters: {', '.join(missing)}"
    
    return True, params, None

@IPCHandlerRegistry.handler('get_config')
def handle_get_config(request: IPCRequest, params: Optional[Dict[str, Any]], py_login:Any) -> str:
    """处理获取配置请求
    
    从配置存储中获取指定键的配置值。
    
    Args:
        request: IPC 请求对象
        params: 请求参数，必须包含 'key' 字段
        
    Returns:
        str: JSON 格式的响应消息
    """
    try:
        # 验证参数
        is_valid, data, error = validate_params(params, ['key'])
        if not is_valid:
            logger.warning(f"Invalid parameters for get_config: {error}")
            return json.dumps(create_error_response(
                request,
                'INVALID_PARAMS',
                error
            ))
        
        # 获取配置
        key = data['key']
        # TODO: 实现实际的配置获取逻辑
        config_value = {'key': key, 'value': 'Config value'}
        
        logger.info(f"Config retrieved: {key}")
        return json.dumps(create_success_response(request, config_value))
    except Exception as e:
        logger.error(f"Error getting config: {e}")
        return json.dumps(create_error_response(
            request,
            'CONFIG_ERROR',
            f"Error getting config: {str(e)}"
        ))

@IPCHandlerRegistry.handler('set_config')
def handle_set_config(request: IPCRequest, params: Optional[Dict[str, Any]], py_login:Any) -> str:
    """处理设置配置请求
    
    将配置值保存到配置存储中。
    
    Args:
        request: IPC 请求对象
        params: 请求参数，必须包含 'key' 和 'value' 字段
        
    Returns:
        str: JSON 格式的响应消息
    """
    try:
        # 验证参数
        is_valid, data, error = validate_params(params, ['key', 'value'])
        if not is_valid:
            logger.warning(f"Invalid parameters for set_config: {error}")
            return json.dumps(create_error_response(
                request,
                'INVALID_PARAMS',
                error
            ))
        
        # 设置配置
        key = data['key']
        value = data['value']
        # TODO: 实现实际的配置设置逻辑
        
        logger.info(f"Config set: {key} = {value}")
        return json.dumps(create_success_response(request, {'success': True}))
    except Exception as e:
        logger.error(f"Error setting config: {e}")
        return json.dumps(create_error_response(
            request,
            'CONFIG_ERROR',
            f"Error setting config: {str(e)}"
        ))

@IPCHandlerRegistry.handler('login')
def handle_login(request: IPCRequest, params: Optional[Dict[str, Any]], py_login:Any) -> str:
    """处理登录请求
    
    验证用户凭据并返回访问令牌。
    
    Args:
        request: IPC 请求对象
        params: 请求参数，必须包含 'username' 和 'password' 字段
        
    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"Login handler called with request: {request}, params: {params}")
        
        # 验证参数
        is_valid, data, error = validate_params(params, ['username', 'password'])
        if not is_valid:
            logger.warning(f"Invalid parameters for login: {error}")
            return json.dumps(create_error_response(
                request,
                'INVALID_PARAMS',
                error
            ))
        
        # 获取用户名和密码
        username = data['username']
        password = data['password']
        print("user name:", username, "password:", password)
        result = py_login.handleLogin(username, password)
        # 简单的密码验证
        if result == 'Successful':
            # 生成随机令牌
            token = str(uuid.uuid4()).replace('-', '')
            logger.info(f"Login successful for user: {username}")
            return json.dumps(create_success_response(request, {
                'token': token,
                'message': 'Login successful'
            }))
        else:
            logger.warning(f"Invalid password for user: {username}")
            return json.dumps(create_error_response(
                request,
                'INVALID_CREDENTIALS',
                'Invalid username or password'
            ))
    except Exception as e:
        logger.error(f"Error in login handler: {e}")
        return json.dumps(create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during login: {str(e)}"
        ))


@IPCHandlerRegistry.handler('get_all')
def handle_get_all(request: IPCRequest, params: Optional[Dict[str, Any]], py_login:Any) -> str:
    """处理登录请求

    验证用户凭据并返回访问令牌。

    Args:
        request: IPC 请求对象
        params: 请求参数，必须包含 'username' 和 'password' 字段

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"Login handler called with request: {request}, params: {params}")

        # 验证参数
        is_valid, data, error = validate_params(params, ['username', 'password'])
        if not is_valid:
            logger.warning(f"Invalid parameters for login: {error}")
            return json.dumps(create_error_response(
                request,
                'INVALID_PARAMS',
                error
            ))

        # 获取用户名和密码
        username = data['username']
        password = data['password']

        # 简单的密码验证
        if password == 'admin123#':
            # 生成随机令牌
            token = str(uuid.uuid4()).replace('-', '')
            logger.info(f"Login successful for user: {username}")
            return json.dumps(create_success_response(request, {
                'token': token,
                'message': 'Login successful'
            }))
        else:
            logger.warning(f"Invalid password for user: {username}")
            return json.dumps(create_error_response(
                request,
                'INVALID_CREDENTIALS',
                'Invalid username or password'
            ))
    except Exception as e:
        logger.error(f"Error in login handler: {e}")
        return json.dumps(create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during login: {str(e)}"
        ))


@IPCHandlerRegistry.handler('get_agents')
def handle_get_agents(request: IPCRequest, params: Optional[list[Any]], py_login:Any) -> str:
    """处理登录请求

    验证用户凭据并返回访问令牌。

    Args:
        request: IPC 请求对象
        params: 请求参数，必须包含 'username' 和 'password' 字段

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"Login handler called with request: {request}, params: {params}")
        print("get agents:", params)
        # 验证参数
        is_valid, data, error = validate_params(params, ['username', 'password'])
        if not is_valid:
            logger.warning(f"Invalid parameters for login: {error}")
            return json.dumps(create_error_response(
                request,
                'INVALID_PARAMS',
                error
            ))

        # 获取用户名和密码
        username = data['username']

        # 简单的密码验证
        # 生成随机令牌
        token = str(uuid.uuid4()).replace('-', '')
        logger.info(f"Login successful for user: {username}")
        return json.dumps([{"id": 666, "name": "john smith"}])

    except Exception as e:
        logger.error(f"Error in login handler: {e}")
        return json.dumps(create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during login: {str(e)}"
        ))



@IPCHandlerRegistry.handler('get_skills')
def handle_get_skills(request: IPCRequest, params: Optional[Dict[str, Any]], py_login:Any) -> str:
    """处理登录请求

    验证用户凭据并返回访问令牌。

    Args:
        request: IPC 请求对象
        params: 请求参数，必须包含 'username' 和 'password' 字段

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"Login handler called with request: {request}, params: {params}")

        # 验证参数
        is_valid, data, error = validate_params(params, ['username', 'password'])
        if not is_valid:
            logger.warning(f"Invalid parameters for login: {error}")
            return json.dumps(create_error_response(
                request,
                'INVALID_PARAMS',
                error
            ))

        # 获取用户名和密码
        username = data['username']
        password = data['password']

        # 简单的密码验证
        if password == 'admin123#':
            # 生成随机令牌
            token = str(uuid.uuid4()).replace('-', '')
            logger.info(f"Login successful for user: {username}")
            return json.dumps(create_success_response(request, {
                'token': token,
                'message': 'Login successful'
            }))
        else:
            logger.warning(f"Invalid password for user: {username}")
            return json.dumps(create_error_response(
                request,
                'INVALID_CREDENTIALS',
                'Invalid username or password'
            ))
    except Exception as e:
        logger.error(f"Error in login handler: {e}")
        return json.dumps(create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during login: {str(e)}"
        ))



@IPCHandlerRegistry.handler('get_tasks')
def handle_get_tasks(request: IPCRequest, params: Optional[Dict[str, Any]], py_login:Any) -> str:
    """处理登录请求

    验证用户凭据并返回访问令牌。

    Args:
        request: IPC 请求对象
        params: 请求参数，必须包含 'username' 和 'password' 字段

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"Login handler called with request: {request}, params: {params}")

        # 验证参数
        is_valid, data, error = validate_params(params, ['username', 'password'])
        if not is_valid:
            logger.warning(f"Invalid parameters for login: {error}")
            return json.dumps(create_error_response(
                request,
                'INVALID_PARAMS',
                error
            ))

        # 获取用户名和密码
        username = data['username']

        # 简单的密码验证
        if username == 'admin123#':
            # 生成随机令牌
            token = str(uuid.uuid4()).replace('-', '')
            logger.info(f"Login successful for user: {username}")
            return json.dumps(create_success_response(request, {
                'token': token,
                'message': 'Login successful'
            }))
        else:
            logger.warning(f"Invalid password for user: {username}")
            return json.dumps(create_error_response(
                request,
                'INVALID_CREDENTIALS',
                'Invalid username or password'
            ))
    except Exception as e:
        logger.error(f"Error in login handler: {e}")
        return json.dumps(create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during login: {str(e)}"
        ))



@IPCHandlerRegistry.handler('get_vehicles')
def handle_get_vehicles(request: IPCRequest, params: Optional[Dict[str, Any]], py_login:Any) -> str:
    """处理登录请求

    验证用户凭据并返回访问令牌。

    Args:
        request: IPC 请求对象
        params: 请求参数，必须包含 'username' 和 'password' 字段

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"Login handler called with request: {request}, params: {params}")

        # 验证参数
        is_valid, data, error = validate_params(params, ['username', 'password'])
        if not is_valid:
            logger.warning(f"Invalid parameters for login: {error}")
            return json.dumps(create_error_response(
                request,
                'INVALID_PARAMS',
                error
            ))

        # 获取用户名和密码
        username = data['username']

        # 简单的密码验证
        if username == 'admin123#':
            # 生成随机令牌
            token = str(uuid.uuid4()).replace('-', '')
            logger.info(f"Login successful for user: {username}")
            return json.dumps(create_success_response(request, {
                'token': token,
                'message': 'Get vehicles successful'
            }))
        else:
            logger.warning(f"Invalid password for user: {username}")
            return json.dumps(create_error_response(
                request,
                'INVALID_CREDENTIALS',
                'Invalid username or password'
            ))
    except Exception as e:
        logger.error(f"Error in login handler: {e}")
        return json.dumps(create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during login: {str(e)}"
        ))


@IPCHandlerRegistry.handler('get_tools')
def handle_get_tools(request: IPCRequest, params: Optional[Dict[str, Any]], py_login:Any) -> str:
    """处理登录请求

    验证用户凭据并返回访问令牌。

    Args:
        request: IPC 请求对象
        params: 请求参数，必须包含 'username' 和 'password' 字段

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"Login handler called with request: {request}, params: {params}")

        # 验证参数
        is_valid, data, error = validate_params(params, ['username', 'password'])
        if not is_valid:
            logger.warning(f"Invalid parameters for login: {error}")
            return json.dumps(create_error_response(
                request,
                'INVALID_PARAMS',
                error
            ))

        # 获取用户名和密码
        username = data['username']

        # 简单的密码验证
        if username == 'admin123#':
            # 生成随机令牌
            token = str(uuid.uuid4()).replace('-', '')
            logger.info(f"Login successful for user: {username}")
            return json.dumps(create_success_response(request, {
                'token': token,
                'message': 'Get tools successful'
            }))
        else:
            logger.warning(f"Invalid password for user: {username}")
            return json.dumps(create_error_response(
                request,
                'INVALID_CREDENTIALS',
                'Invalid username or password'
            ))
    except Exception as e:
        logger.error(f"Error in login handler: {e}")
        return json.dumps(create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during login: {str(e)}"
        ))


@IPCHandlerRegistry.handler('get_chats')
def handle_get_chats(request: IPCRequest, params: Optional[Dict[str, Any]], py_login:Any) -> str:
    """处理登录请求

    验证用户凭据并返回访问令牌。

    Args:
        request: IPC 请求对象
        params: 请求参数，必须包含 'username' 和 'password' 字段

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"Login handler called with request: {request}, params: {params}")

        # 验证参数
        is_valid, data, error = validate_params(params, ['username', 'password'])
        if not is_valid:
            logger.warning(f"Invalid parameters for login: {error}")
            return json.dumps(create_error_response(
                request,
                'INVALID_PARAMS',
                error
            ))

        # 获取用户名和密码
        username = data['username']

        # 简单的密码验证
        if username == 'admin123#':
            # 生成随机令牌
            token = str(uuid.uuid4()).replace('-', '')
            logger.info(f"Login successful for user: {username}")
            return json.dumps(create_success_response(request, {
                'token': token,
                'message': 'Login successful'
            }))
        else:
            logger.warning(f"Invalid password for user: {username}")
            return json.dumps(create_error_response(
                request,
                'INVALID_CREDENTIALS',
                'Invalid username or password'
            ))
    except Exception as e:
        logger.error(f"Error in login handler: {e}")
        return json.dumps(create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during login: {str(e)}"
        ))


@IPCHandlerRegistry.handler('save_agents')
def handle_save_agents(request: IPCRequest, params: Optional[list[Any]], py_login:Any) -> str:
    """处理登录请求

    验证用户凭据并返回访问令牌。

    Args:
        request: IPC 请求对象
        params: 请求参数，必须包含 'username' 和 'password' 字段

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"Login handler called with request: {request}, params: {params}")
        print("save agents:", params)
        # 验证参数
        is_valid, data, error = validate_params(params, ['username', 'password'])
        if not is_valid:
            logger.warning(f"Invalid parameters for login: {error}")
            return json.dumps(create_error_response(
                request,
                'INVALID_PARAMS',
                error
            ))

        # 获取用户名和密码
        username = data['username']


        # 生成随机令牌
        token = str(uuid.uuid4()).replace('-', '')
        logger.info(f"Login successful for user: {username}")
        return json.dumps(create_success_response(request, {
            'token': token,
            'message': 'Get agents successful'
        }))

    except Exception as e:
        logger.error(f"Error in login handler: {e}")
        return json.dumps(create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during login: {str(e)}"
        ))


# 打印所有已注册的处理器
logger.info(f"Registered handlers: {IPCHandlerRegistry.list_handlers()}")