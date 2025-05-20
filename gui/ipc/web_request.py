from typing import Any, Dict, Optional, Callable, List
from utils.logger_helper import logger_helper
import json

class WebRequestHandler:
    """统一的 Web 请求处理类，用于管理所有发送到 Web 的请求"""
    
    def __init__(self, ipc_handler):
        self.ipc_handler = ipc_handler
        self._event_handlers: Dict[str, List[Callable]] = {}
        self._state = {}
    
    def send_event(self, event_type: str, data: Dict[str, Any] = None):
        """发送事件到 Web"""
        try:
            message = {
                'type': 'event',
                'eventType': event_type,
                'data': data or {}
            }
            self.ipc_handler.sendToJavaScript(message)
            logger_helper.info(f"Sent event to Web: {event_type}")
        except Exception as e:
            logger_helper.error(f"Error sending event to Web: {e}")
    
    def update_state(self, state_key: str, value: Any):
        """更新状态并发送到 Web"""
        try:
            self._state[state_key] = value
            self.send_event('state_update', {
                'key': state_key,
                'value': value
            })
            logger_helper.info(f"Updated state: {state_key} = {value}")
        except Exception as e:
            logger_helper.error(f"Error updating state: {e}")
    
    def get_state(self, state_key: str) -> Any:
        """获取状态值"""
        return self._state.get(state_key)
    
    def register_event_handler(self, event_type: str, handler: Callable):
        """注册事件处理器"""
        if event_type not in self._event_handlers:
            self._event_handlers[event_type] = []
        self._event_handlers[event_type].append(handler)
        logger_helper.info(f"Registered event handler for: {event_type}")
    
    def unregister_event_handler(self, event_type: str, handler: Callable):
        """移除事件处理器"""
        if event_type in self._event_handlers:
            self._event_handlers[event_type].remove(handler)
            logger_helper.info(f"Unregistered event handler for: {event_type}")
    
    def handle_web_event(self, event_type: str, data: Dict[str, Any]):
        """处理来自 Web 的事件"""
        if event_type in self._event_handlers:
            for handler in self._event_handlers[event_type]:
                try:
                    handler(data)
                except Exception as e:
                    logger_helper.error(f"Error in event handler for {event_type}: {e}")
    
    # 预定义的 Web 请求方法
    def show_notification(self, title: str, message: str, type: str = 'info'):
        """显示通知"""
        self.send_event('notification', {
            'title': title,
            'message': message,
            'type': type
        })
    
    def show_loading(self, message: str = 'Loading...'):
        """显示加载状态"""
        self.send_event('loading', {
            'message': message,
            'show': True
        })
    
    def hide_loading(self):
        """隐藏加载状态"""
        self.send_event('loading', {
            'show': False
        })
    
    def update_progress(self, progress: float, message: str = None):
        """更新进度"""
        self.send_event('progress', {
            'progress': progress,
            'message': message
        })
    
    def show_error(self, message: str):
        """显示错误消息"""
        self.send_event('error', {
            'message': message
        })
    
    def show_success(self, message: str):
        """显示成功消息"""
        self.send_event('success', {
            'message': message
        })
    
    def update_ui_state(self, component_id: str, state: Dict[str, Any]):
        """更新 UI 组件状态"""
        self.send_event('ui_update', {
            'componentId': component_id,
            'state': state
        })
    
    def refresh_data(self, data_type: str, data: Any):
        """刷新数据"""
        self.send_event('data_refresh', {
            'type': data_type,
            'data': data
        })
    
    def execute_script(self, script: str):
        """执行 JavaScript 代码"""
        self.ipc_handler.sendToJavaScript({
            'type': 'command',
            'command': 'execute_script',
            'params': {
                'script': script
            }
        })
    
    def reload_page(self):
        """重新加载页面"""
        self.ipc_handler.sendToJavaScript({
            'type': 'command',
            'command': 'reload'
        })
    
    def toggle_dev_tools(self):
        """切换开发者工具"""
        self.ipc_handler.sendToJavaScript({
            'type': 'command',
            'command': 'toggle_dev_tools'
        })
    
    def clear_logs(self):
        """清除日志"""
        self.ipc_handler.sendToJavaScript({
            'type': 'command',
            'command': 'clear_logs'
        })
    
    def get_page_info(self) -> Dict[str, Any]:
        """获取页面信息"""
        return self.ipc_handler.sendToJavaScript({
            'type': 'request',
            'request': 'get_page_info'
        })
    
    def get_console_logs(self) -> str:
        """获取控制台日志"""
        return self.ipc_handler.sendToJavaScript({
            'type': 'request',
            'request': 'get_console_logs'
        })
    
    def get_network_logs(self) -> str:
        """获取网络日志"""
        return self.ipc_handler.sendToJavaScript({
            'type': 'request',
            'request': 'get_network_logs'
        })
    
    def get_element_logs(self) -> str:
        """获取元素日志"""
        return self.ipc_handler.sendToJavaScript({
            'type': 'request',
            'request': 'get_element_logs'
        }) 