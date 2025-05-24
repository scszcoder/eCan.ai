"""
IPC 服务模块，处理与前端的数据交互
"""

from PySide6.QtCore import QObject, Slot, Signal
from utils.logger_helper import logger_helper
import json
from typing import Optional, Dict, Any, Callable
from .types import (
    IPCRequest, IPCResponse, create_request, create_error_response
)
from .registry import IPCHandlerRegistry

logger = logger_helper.logger

class IPCService(QObject):
    """IPC 服务类，处理与前端的数据交互"""
    
    # 定义信号
    python_to_web = Signal(str)  # 发送消息到 Web 的信号
    
    def __init__(self):
        super().__init__()
        logger.info("IPC service initialized")
        # 存储请求ID和对应的回调函数的映射
        self._request_callbacks: Dict[str, Callable[[IPCResponse], None]] = {}
    
    @Slot(str, result=str)
    def web_to_python(self, message: str) -> str:
        """处理来自 Web 的消息
        
        Args:
            message: JSON 格式的消息字符串
            
        Returns:
            str: JSON 格式的响应消息
        """
        try:
            # 解析消息
            data = json.loads(message)
            logger.info(f"Received message: {data}")

            # 检查消息类型
            if 'type' not in data:
                logger.warning("Message missing type field")
                return json.dumps(create_error_response(
                    {'id': 'missing_type', 'method': 'unknown'},
                    'MISSING_TYPE',
                    "Message missing type field"
                ))
            
            # 处理响应消息
            if data['type'] == 'response':
                response = IPCResponse(**data)
                self._handle_response(response)
                return json.dumps({"status": "ok"})
            
            # 处理请求消息
            if data['type'] == 'request':
                request = IPCRequest(**data)
                return self._handle_request(request)
            
            # 未知消息类型
            logger.warning(f"Unknown message type: {data['type']}")
            return json.dumps(create_error_response(
                {'id': 'unknown_type', 'method': 'unknown'},
                'UNKNOWN_TYPE',
                f"Unknown message type: {data['type']}"
            ))
                
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            return json.dumps(create_error_response(
                {'id': 'parse_error', 'method': 'unknown'},
                'PARSE_ERROR',
                f"Invalid JSON format: {str(e)}"
            ))
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            return json.dumps(create_error_response(
                {'id': 'internal_error', 'method': 'unknown'},
                'INTERNAL_ERROR',
                f"Error processing message: {str(e)}"
            ))
    
    def _handle_request(self, request: IPCRequest) -> str:
        """处理 IPC 请求
        
        Args:
            request: IPC 请求对象
            
        Returns:
            str: JSON 格式的响应消息
        """
        method = request.get('method')
        params = request.get('params')
        
        if not method:
            return json.dumps(create_error_response(
                request,
                'INVALID_REQUEST',
                "Missing method in request"
            ))
        
        # 查找并调用对应的处理器
        handler = IPCHandlerRegistry.get_handler(method)
        if handler:
            try:
                # 直接调用处理器，让装饰器处理参数
                return handler(request, params)
            except Exception as e:
                logger.error(f"Error calling handler for method {method}: {e}")
                return json.dumps(create_error_response(
                    request,
                    'HANDLER_ERROR',
                    f"Error calling handler: {str(e)}"
                ))
        else:
            return json.dumps(create_error_response(
                request,
                'METHOD_NOT_FOUND',
                f"Unknown method: {method}"
            ))
    
    def _handle_response(self, response: IPCResponse) -> None:
        """处理响应
        
        Args:
            response: 响应对象
        """
        try:
            # 获取对应的回调函数
            callback = self._request_callbacks.get(response['id'])
            if callback:
                # 调用回调函数处理响应
                callback(response)
                # 处理完成后删除回调
                del self._request_callbacks[response['id']]
                logger.info(f"Response handled for request: {response['id']}")
            else:
                logger.warning(f"No callback found for response: {response['id']}")
        except Exception as e:
            logger.error(f"Error handling response: {e}")
    
    def send_request(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        meta: Optional[Dict[str, Any]] = None,
        callback: Optional[Callable[[IPCResponse], None]] = None
    ) -> None:
        """发送请求到 Web
        
        Args:
            method: 方法名
            params: 请求参数
            meta: 元数据
            callback: 响应回调函数
        """
        try:
            # 创建请求
            request = create_request(method, params, meta)
            
            # 如果有回调函数，注册回调
            if callback:
                self._request_callbacks[request['id']] = callback
                logger.debug(f"Callback registered for request: {request['id']}")
            
            # 发送请求
            self.python_to_web.emit(json.dumps(request))
            logger.debug(f"Request sent: {json.dumps(request)}")
        except Exception as e:
            logger.error(f"Error sending request: {e}")
            if callback:
                error_response = create_error_response(
                    request,
                    'REQUEST_ERROR',
                    str(e)
                )
                callback(error_response) 