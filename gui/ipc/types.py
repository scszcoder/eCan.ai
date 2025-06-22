"""
IPC 通信类型定义
"""

from typing import TypedDict, Union, Optional, Dict, Any, Literal
from datetime import datetime
import uuid

# IPC 错误信息
class IPCError(TypedDict):
    code: Union[int, str]  # 错误码
    message: str          # 错误描述
    details: Optional[Any]  # 额外错误上下文

# IPC 请求
class IPCRequest(TypedDict):
    id: str              # 全局唯一请求标识
    type: Literal['request', 'response']  # 请求类型
    method: str          # 要调用的接口名
    params: Optional[Any]  # 请求参数
    meta: Optional[Dict[str, Any]]  # 扩展元信息
    timestamp: Optional[int]  # 发送时间戳 ms

# IPC 响应
class IPCResponse(TypedDict):
    id: str              # 与请求相同的 ID
    method: Optional[str]  # 回显请求的 method
    status: Literal['success', 'pending', 'error']  # 调用结果状态
    result: Optional[Any]  # 正常返回的数据（status=success 时必填）
    error: Optional[IPCError]  # 错误信息（status=error 时必填）
    meta: Optional[Dict[str, Any]]  # 扩展元信息
    timestamp: Optional[int]  # 发送时间戳 ms

def create_request(method: str, params: Optional[Any] = None, meta: Optional[Dict[str, Any]] = None) -> IPCRequest:
    """创建 IPC 请求
    
    Args:
        method: 要调用的接口名
        params: 请求参数
        meta: 扩展元信息
        
    Returns:
        IPCRequest: 请求对象
    """
    return {
        'id': str(uuid.uuid4()),
        'type': 'request',
        'method': method,
        'params': params,
        'meta': meta,
        'timestamp': int(datetime.now().timestamp() * 1000)
    }

def create_success_response(request: IPCRequest, result: Any, meta: Optional[Dict[str, Any]] = None) -> IPCResponse:
    """创建成功响应
    
    Args:
        request: 原始请求
        result: 返回结果
        meta: 扩展元信息
        
    Returns:
        IPCResponse: 响应对象
    """
    return {
        'id': request['id'],
        'type': 'response',
        'method': request['method'],
        'status': 'success',
        'result': result,
        'meta': meta,
        'timestamp': int(datetime.now().timestamp() * 1000)
    }

def create_error_response(request: IPCRequest, code: Union[int, str], message: str, details: Optional[Any] = None, meta: Optional[Dict[str, Any]] = None) -> IPCResponse:
    """创建错误响应
    
    Args:
        request: 原始请求
        code: 错误码
        message: 错误描述
        details: 额外错误上下文
        meta: 扩展元信息
        
    Returns:
        IPCResponse: 响应对象
    """
    return {
        'id': request['id'],
        'type': 'response',
        'method': request['method'],
        'status': 'error',
        'error': {
            'code': code,
            'message': message,
            'details': details
        },
        'meta': meta,
        'timestamp': int(datetime.now().timestamp() * 1000)
    }

def create_pending_response(request: IPCRequest, message: str, details: Any = None, meta: Optional[Dict[str, Any]] = None) -> IPCResponse:
    """创建 pending 响应
    
    Args:
        request: 原始请求
        message: 描述信息
        details: 额外信息
        meta: 扩展元信息
    Returns:
        IPCResponse: 响应对象
    """
    return {
        'id': request['id'],
        'type': 'response',
        'method': request['method'],
        'status': 'pending',
        'result': {
            'message': message,
            'details': details
        },
        'meta': meta,
        'timestamp': int(datetime.now().timestamp() * 1000)
    } 