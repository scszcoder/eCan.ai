"""
IPC 通信类型定义
"""

from typing import TypedDict, Literal, Union, Optional, Dict, Any
from datetime import datetime

# 消息类型
MessageType = Literal['message', 'config', 'command', 'event']

# 基础消息
class BaseMessage(TypedDict):
    type: MessageType
    timestamp: str

# 普通消息
class TextMessage(BaseMessage):
    type: Literal['message']
    content: str

# 配置操作消息
class ConfigMessage(BaseMessage):
    type: Literal['config']
    action: Literal['get', 'set']
    key: str
    value: Optional[str]

# 命令执行消息
class CommandMessage(BaseMessage):
    type: Literal['command']
    command: str
    args: Optional[Dict[str, Any]]

# 事件通知消息
class EventMessage(BaseMessage):
    type: Literal['event']
    event: str
    data: Optional[Dict[str, Any]]

# 所有可能的消息类型
IPCMessage = Union[TextMessage, ConfigMessage, CommandMessage, EventMessage]

# 响应状态
ResponseStatus = Literal['success', 'error']

# 基础响应
class BaseResponse(TypedDict):
    status: ResponseStatus
    timestamp: str

# 成功响应
class SuccessResponse(BaseResponse):
    status: Literal['success']
    data: Optional[Any]
    message: Optional[str]

# 错误响应
class ErrorResponse(BaseResponse):
    status: Literal['error']
    message: str
    code: Optional[str]

# 所有可能的响应类型
IPCResponse = Union[SuccessResponse, ErrorResponse]

# 配置响应数据
class ConfigData(TypedDict):
    key: str
    value: str

# 命令响应数据
class CommandData(TypedDict):
    command: str
    result: Any

# 事件响应数据
class EventData(TypedDict):
    event: str
    data: Any

def create_response(
    status: ResponseStatus,
    message: Optional[str] = None,
    data: Optional[Any] = None,
    code: Optional[str] = None
) -> IPCResponse:
    """创建响应对象
    
    Args:
        status: 响应状态
        message: 响应消息
        data: 响应数据
        code: 错误代码（仅用于错误响应）
        
    Returns:
        IPCResponse: 响应对象
    """
    timestamp = datetime.now().isoformat()
    
    if status == 'success':
        return {
            'status': 'success',
            'timestamp': timestamp,
            'message': message,
            'data': data
        }
    else:
        return {
            'status': 'error',
            'timestamp': timestamp,
            'message': message or 'Unknown error',
            'code': code
        } 