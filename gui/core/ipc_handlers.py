"""
IPC 处理器实现模块
"""

from typing import Any, Optional, Dict
from gui.core.ipc_types import IPCRequest, create_success_response, create_error_response
from gui.core.ipc_handler_registry import IPCHandlerRegistry
from utils.logger_helper import logger_helper
import json

logger = logger_helper.logger

def validate_params(params: Optional[Dict[str, Any]], required_keys: list[str]) -> tuple[bool, Optional[str]]:
    """验证参数
    
    Args:
        params: 参数字典
        required_keys: 必需的键列表
        
    Returns:
        tuple[bool, Optional[str]]: (是否有效, 错误信息)
    """
    if not params:
        return False, "Missing parameters"
    
    for key in required_keys:
        if key not in params:
            return False, f"Missing required parameter: {key}"
    
    return True, None

@IPCHandlerRegistry.register('get_config')
def handle_get_config(self: 'IPCService', request: IPCRequest, params: Optional[Dict[str, Any]]) -> str:
    """处理获取配置请求"""
    try:
        # 验证参数
        is_valid, error_msg = validate_params(params, ['key'])
        if not is_valid:
            return json.dumps(create_error_response(
                request,
                'INVALID_PARAMS',
                error_msg
            ))
        
        # 获取配置
        key = params['key']
        # TODO: 实现实际的配置获取逻辑
        result = {'key': key, 'value': 'Config value'}
        
        logger.info(f"Config retrieved: {key}")
        return json.dumps(create_success_response(request, result))
    except Exception as e:
        logger.error(f"Error getting config: {e}")
        return json.dumps(create_error_response(
            request,
            'CONFIG_ERROR',
            f"Error getting config: {str(e)}"
        ))

@IPCHandlerRegistry.register('set_config')
def handle_set_config(self: 'IPCService', request: IPCRequest, params: Optional[Dict[str, Any]]) -> str:
    """处理设置配置请求"""
    try:
        # 验证参数
        is_valid, error_msg = validate_params(params, ['key', 'value'])
        if not is_valid:
            return json.dumps(create_error_response(
                request,
                'INVALID_PARAMS',
                error_msg
            ))
        
        # 设置配置
        key = params['key']
        value = params['value']
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