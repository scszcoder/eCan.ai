"""
IPC 处理器实现模块
提供各种 IPC 请求的具体处理实现
"""

from typing import Any, Optional, Dict, TypeVar, Generic, Union
from .types import IPCRequest, create_success_response, create_error_response
from .registry import IPCHandlerRegistry
from utils.logger_helper import logger_helper
import json
import uuid

logger = logger_helper.logger

# 定义泛型类型
T = TypeVar('T')

class ValidationResult(Generic[T]):
    """参数验证结果类"""
    def __init__(self, is_valid: bool, data: Optional[T] = None, error: Optional[str] = None):
        self.is_valid = is_valid
        self.data = data
        self.error = error

def validate_params(params: Optional[Dict[str, Any]], required_keys: list[str]) -> ValidationResult[Dict[str, Any]]:
    """验证请求参数
    
    检查参数字典是否包含所有必需的键。
    
    Args:
        params: 参数字典
        required_keys: 必需的键列表
        
    Returns:
        ValidationResult: 验证结果，包含验证状态、数据（如果有效）和错误信息（如果无效）
        
    Example:
        result = validate_params(params, ['key', 'value'])
        if not result.is_valid:
            return create_error_response(request, 'INVALID_PARAMS', result.error)
    """
    if not params:
        return ValidationResult(False, error="Missing parameters")
    
    missing_keys = [key for key in required_keys if key not in params]
    if missing_keys:
        return ValidationResult(False, error=f"Missing required parameters: {', '.join(missing_keys)}")
    
    return ValidationResult(True, data=params)

@IPCHandlerRegistry.register('get_config')
def handle_get_config(request: IPCRequest, params: Optional[Dict[str, Any]]) -> str:
    """处理获取配置请求
    
    从配置存储中获取指定键的配置值。
    
    Args:
        request: IPC 请求对象
        params: 请求参数，必须包含 'key' 字段
        
    Returns:
        str: JSON 格式的响应消息
        
    Example:
        请求:
        {
            "method": "get_config",
            "params": {"key": "theme"}
        }
        
        成功响应:
        {
            "status": "ok",
            "result": {"key": "theme", "value": "dark"}
        }
        
        错误响应:
        {
            "status": "error",
            "error": {
                "code": "CONFIG_ERROR",
                "message": "Error getting config: Config not found"
            }
        }
    """
    try:
        # 验证参数
        result = validate_params(params, ['key'])
        if not result.is_valid:
            logger.warning(f"Invalid parameters for get_config: {result.error}")
            return json.dumps(create_error_response(
                request,
                'INVALID_PARAMS',
                result.error
            ))
        
        # 获取配置
        key = result.data['key']
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

@IPCHandlerRegistry.register('set_config')
def handle_set_config(request: IPCRequest, params: Optional[Dict[str, Any]]) -> str:
    """处理设置配置请求
    
    将配置值保存到配置存储中。
    
    Args:
        request: IPC 请求对象
        params: 请求参数，必须包含 'key' 和 'value' 字段
        
    Returns:
        str: JSON 格式的响应消息
        
    Example:
        请求:
        {
            "method": "set_config",
            "params": {"key": "theme", "value": "dark"}
        }
        
        成功响应:
        {
            "status": "ok",
            "result": {"success": true}
        }
        
        错误响应:
        {
            "status": "error",
            "error": {
                "code": "CONFIG_ERROR",
                "message": "Error setting config: Invalid value"
            }
        }
    """
    try:
        # 验证参数
        result = validate_params(params, ['key', 'value'])
        if not result.is_valid:
            logger.warning(f"Invalid parameters for set_config: {result.error}")
            return json.dumps(create_error_response(
                request,
                'INVALID_PARAMS',
                result.error
            ))
        
        # 设置配置
        key = result.data['key']
        value = result.data['value']
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

@IPCHandlerRegistry.register('login')
def handle_login(request: IPCRequest, params: Optional[Dict[str, Any]]) -> str:
    """处理登录请求
    
    验证用户凭据并返回访问令牌。
    
    Args:
        request: IPC 请求对象
        params: 请求参数，必须包含 'username' 和 'password' 字段
        
    Returns:
        str: JSON 格式的响应消息
        
    Example:
        请求:
        {
            "method": "login",
            "params": {"username": "admin", "password": "admin123#"}
        }
        
        成功响应:
        {
            "status": "ok",
            "result": {
                "token": "32位随机token",
                "message": "Login successful"
            }
        }
        
        错误响应:
        {
            "status": "error",
            "error": {
                "code": "INVALID_CREDENTIALS",
                "message": "Invalid username or password"
            }
        }
    """
    try:
        # 验证参数
        result = validate_params(params, ['username', 'password'])
        if not result.is_valid:
            logger.warning(f"Invalid parameters for login: {result.error}")
            return json.dumps(create_error_response(
                request,
                'INVALID_PARAMS',
                result.error
            ))
        
        # 获取用户名和密码
        username = result.data['username']
        password = result.data['password']
        
        # 简单的密码验证
        if password == 'admin123#':
            # 生成32位随机token
            token = uuid.uuid4().hex
            logger.info(f"User {username} logged in successfully")
            return json.dumps(create_success_response(request, {
                'token': token,
                'message': 'Login successful'
            }))
        else:
            logger.warning(f"Invalid login attempt for user {username}")
            return json.dumps(create_error_response(
                request,
                'INVALID_CREDENTIALS',
                'Invalid username or password'
            ))
    except Exception as e:
        logger.error(f"Error during login: {e}")
        return json.dumps(create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during login: {str(e)}"
        ))

# 注册所有处理方法
HANDLERS = {
    'login': handle_login,
    # ... 其他处理方法 ...
}