"""
请求拦截器模块，用于拦截和处理 Web 请求
"""

from PySide6.QtWebEngineCore import QWebEngineUrlRequestInterceptor
from PySide6.QtCore import QUrl
from utils.logger_helper import logger_helper
from typing import Optional, Dict, Any

class RequestInterceptor(QWebEngineUrlRequestInterceptor):
    """请求拦截器类，用于拦截和处理 Web 请求"""
    
    def __init__(self):
        super().__init__()
        self._request_count: int = 0
        self._blocked_count: int = 0
        self._allowed_domains: set[str] = set()
        self._blocked_domains: set[str] = set()
        self._custom_headers: Dict[str, str] = {}
    
    def interceptRequest(self, info):
        """拦截请求"""
        try:
            self._request_count += 1
            
            # 获取请求信息
            url = info.requestUrl().toString()
            method = info.requestMethod().data().decode()
            resource_type = info.resourceType().name
            
            # 记录请求信息
            # logger_helper.debug(
            #     f"Intercepted request: {method} {url} ({resource_type})"
            # )
            
            # 检查是否需要拦截
            if self._should_intercept(url, resource_type):
                self._blocked_count += 1
                logger_helper.info(f"Blocked request: {url}")
                info.block(True)
                return
            
            # 添加自定义请求头
            self._add_custom_headers(info)
            
        except Exception as e:
            logger_helper.error(f"Error in request interceptor: {str(e)}")
    
    def _should_intercept(self, url: str, resource_type: str) -> bool:
        """检查是否需要拦截请求"""
        # 检查域名
        domain = QUrl(url).host()
        
        # 检查是否在允许列表中
        if self._allowed_domains and domain not in self._allowed_domains:
            return True
        
        # 检查是否在阻止列表中
        if domain in self._blocked_domains:
            return True
        
        # 检查资源类型
        blocked_types = {
            'IMAGE',
            'MEDIA',
            'FONT',
            'PING',
            'CSP_REPORT',
            'PREFETCH',
            'FAVICON'
        }
        
        return resource_type in blocked_types
    
    def _add_custom_headers(self, info):
        """添加自定义请求头"""
        for key, value in self._custom_headers.items():
            info.setHttpHeader(key.encode(), value.encode())
    
    def add_allowed_domain(self, domain: str):
        """添加允许的域名"""
        self._allowed_domains.add(domain)
        logger_helper.info(f"Added allowed domain: {domain}")
    
    def add_blocked_domain(self, domain: str):
        """添加阻止的域名"""
        self._blocked_domains.add(domain)
        logger_helper.info(f"Added blocked domain: {domain}")
    
    def set_custom_header(self, key: str, value: str):
        """设置自定义请求头"""
        self._custom_headers[key] = value
        logger_helper.info(f"Set custom header: {key}: {value}")
    
    def clear_custom_headers(self):
        """清除所有自定义请求头"""
        self._custom_headers.clear()
        logger_helper.info("Cleared all custom headers")
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            'total_requests': self._request_count,
            'blocked_requests': self._blocked_count,
            'allowed_domains': list(self._allowed_domains),
            'blocked_domains': list(self._blocked_domains),
            'custom_headers': self._custom_headers.copy()
        }
    
    def reset_statistics(self):
        """重置统计信息"""
        self._request_count = 0
        self._blocked_count = 0
        logger_helper.info("Reset request statistics") 