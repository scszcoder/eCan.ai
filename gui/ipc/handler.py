from PySide6.QtCore import QObject, Signal, Slot, Property
import json
import logging
from typing import Any, Dict, Optional, Callable
from utils.logger_helper import logger_helper
import datetime

class IPCHandler(QObject):
    """统一的 IPC 处理类，用于管理所有的 IPC 通信"""
    
    # 信号定义
    dataReceived = Signal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._data = ""
        self.parent = parent
        self.command_handlers = {}
        self.request_handlers = {}
        
        # 注册默认的命令处理器
        self.register_default_handlers()
    
    @Property(str)
    def data(self):
        return self._data
    
    @data.setter
    def data(self, value):
        self._data = value
        self.dataReceived.emit(value)
    
    def register_default_handlers(self):
        """注册默认的命令和请求处理器"""
        # 注册一个示例命令处理器
        self.register_command('test_command', self.handle_test_command)
        
        # 注册一个示例请求处理器
        self.register_request('test_request', self.handle_test_request)
    
    def register_command(self, command: str, handler: Callable):
        """注册命令处理器"""
        self.command_handlers[command] = handler
        logger_helper.info(f"Registered command handler for: {command}")
    
    def register_request(self, request: str, handler: Callable):
        """注册请求处理器"""
        self.request_handlers[request] = handler
        logger_helper.info(f"Registered request handler for: {request}")
    
    @Slot(str)
    def sendToPython(self, message: str):
        """处理来自 JavaScript 的消息"""
        try:
            data = json.loads(message)
            logger_helper.info(f"Received from JavaScript: {data}")
            
            message_type = data.get('type')
            if message_type == 'command':
                self.handle_command(data)
            elif message_type == 'request':
                self.handle_request(data)
            else:
                logger_helper.warning(f"Unknown message type: {message_type}")
                
        except json.JSONDecodeError:
            logger_helper.error(f"Invalid JSON from JavaScript: {message}")
        except Exception as e:
            logger_helper.error(f"Error processing message: {str(e)}")
    
    def handle_command(self, data: Dict[str, Any]):
        """处理命令消息"""
        command = data.get('command')
        command_data = data.get('data', {})
        
        if command in self.command_handlers:
            try:
                self.command_handlers[command](command_data)
            except Exception as e:
                self.send_response('error', {'error': f'Command error: {str(e)}'})
        else:
            self.send_response('error', {'error': f'Unknown command: {command}'})
    
    def handle_request(self, data: Dict[str, Any]):
        """处理请求消息"""
        request_type = data.get('requestType')
        request_data = data.get('data', {})
        
        if request_type in self.request_handlers:
            try:
                result = self.request_handlers[request_type](request_data)
                self.send_response(request_type, {'result': result})
            except Exception as e:
                self.send_response('error', {'error': f'Request error: {str(e)}'})
        else:
            self.send_response('error', {'error': f'Unknown request type: {request_type}'})
    
    def send_response(self, response_type: str, data: Dict[str, Any]):
        """发送响应到 JavaScript"""
        response = {
            'type': 'response',
            'responseType': response_type,
            **data
        }
        self.data = json.dumps(response)
    
    # 示例命令处理器
    def handle_test_command(self, data: Dict[str, Any]):
        """处理测试命令"""
        message = data.get('message', '')
        self.send_response('command_result', {
            'result': f'Command received: {message}',
            'timestamp': str(datetime.datetime.now())
        })
    
    # 示例请求处理器
    def handle_test_request(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """处理测试请求"""
        message = data.get('message', '')
        return {
            'message': f'Request received: {message}',
            'timestamp': str(datetime.datetime.now())
        } 