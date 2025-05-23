"""
IPC 服务模块，处理与前端的数据交互
"""

from PySide6.QtCore import QObject, Slot, Signal
from typing import Any, Dict, Optional
from utils.logger_helper import logger_helper
import json
from datetime import datetime
from .ipc_types import (
    IPCMessage, IPCResponse, TextMessage, ConfigMessage,
    CommandMessage, EventMessage, create_response
)

logger = logger_helper.logger

class IPCService(QObject):
    """IPC 服务类，处理与前端的数据交互"""
    
    # 定义信号
    python_to_web = Signal(dict)  # 接收消息信号
    
    def __init__(self):
        super().__init__()
        logger.info("IPC service initialized")
    
    @Slot(str, result=str)
    def web_to_python(self, message: str) -> str:
        """发送消息到 Python
        
        Args:
            message: JSON 格式的消息字符串
            
        Returns:
            str: JSON 格式的响应消息
        """
        try:
            # 解析消息
            data: IPCMessage = json.loads(message)
            logger.info(f"Received message: {data}")
            
            # 发送信号
            self.python_to_web.emit(data)
            
            # 根据消息类型处理
            if data['type'] == 'message':
                return self._handle_text_message(data)
            elif data['type'] == 'config':
                return self._handle_config_message(data)
            elif data['type'] == 'command':
                return self._handle_command_message(data)
            elif data['type'] == 'event':
                return self._handle_event_message(data)
            else:
                return json.dumps(create_response(
                    'error',
                    f"Unknown message type: {data['type']}"
                ))
                
        except json.JSONDecodeError as e:
            return json.dumps(create_response(
                'error',
                f"Invalid JSON format: {str(e)}"
            ))
        except Exception as e:
            return json.dumps(create_response(
                'error',
                f"Error processing message: {str(e)}"
            ))
    
    def _handle_text_message(self, message: TextMessage) -> str:
        """处理文本消息"""
        return json.dumps(create_response(
            'success',
            "Message received",
            message
        ))
    
    def _handle_config_message(self, message: ConfigMessage) -> str:
        """处理配置消息"""
        try:
            if message['action'] == 'get':
                # TODO: 实现配置获取逻辑
                return json.dumps(create_response(
                    'success',
                    data={'key': message['key'], 'value': f"Config value for {message['key']}"}
                ))
            else:  # set
                # TODO: 实现配置设置逻辑
                return json.dumps(create_response(
                    'success',
                    "Config updated"
                ))
        except Exception as e:
            return json.dumps(create_response(
                'error',
                f"Error handling config message: {str(e)}"
            ))
    
    def _handle_command_message(self, message: CommandMessage) -> str:
        """处理命令消息"""
        try:
            # TODO: 实现命令处理逻辑
            return json.dumps(create_response(
                'success',
                data={
                    'command': message['command'],
                    'result': f"Executed command: {message['command']}"
                }
            ))
        except Exception as e:
            return json.dumps(create_response(
                'error',
                f"Error handling command message: {str(e)}"
            ))
    
    def _handle_event_message(self, message: EventMessage) -> str:
        """处理事件消息"""
        try:
            # TODO: 实现事件处理逻辑
            return json.dumps(create_response(
                'success',
                data={
                    'event': message['event'],
                    'data': message.get('data', {})
                }
            ))
        except Exception as e:
            return json.dumps(create_response(
                'error',
                f"Error handling event message: {str(e)}"
            )) 