"""
请求拦截器模块，处理网络请求的拦截和修改
"""

from PySide6.QtWebEngineCore import QWebEngineUrlRequestInterceptor
from utils.logger_helper import logger_helper

class RequestInterceptor(QWebEngineUrlRequestInterceptor):
    """请求拦截器类，用于拦截和修改网络请求"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
    
    def interceptRequest(self, info):
        """拦截请求并添加必要的头信息"""
        # 添加 CORS 头
        info.setHttpHeader(b"Access-Control-Allow-Origin", b"*")
        info.setHttpHeader(b"Access-Control-Allow-Methods", b"GET, POST, PUT, DELETE, OPTIONS")
        info.setHttpHeader(b"Access-Control-Allow-Headers", b"Content-Type, Authorization")
        info.setHttpHeader(b"Access-Control-Allow-Credentials", b"true")
        
        # 记录请求信息
        logger_helper.debug(f"Intercepted request: {info.requestMethod().data().decode()} {info.requestUrl().toString()}") 