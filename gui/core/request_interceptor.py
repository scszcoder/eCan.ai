"""
Request Interceptor module for intercepting and handling Web requests
"""

from PySide6.QtWebEngineCore import QWebEngineUrlRequestInterceptor
from PySide6.QtCore import QUrl
from utils.logger_helper import logger_helper as logger
from typing import Optional, Dict, Any

class RequestInterceptor(QWebEngineUrlRequestInterceptor):
    """Request Interceptor class for intercepting and handling Web requests"""
    
    def __init__(self):
        super().__init__()
        self._request_count: int = 0
        self._blocked_count: int = 0
        self._allowed_domains: set[str] = set()
        self._blocked_domains: set[str] = set()
        self._custom_headers: Dict[str, str] = {}
    
    def interceptRequest(self, info):
        """Intercept requests"""
        try:
            self._request_count += 1

            # Get request information
            url = info.requestUrl().toString()
            method = info.requestMethod().data().decode()
            resource_type = info.resourceType().name

            # Log request information
            # logger_helper.debug(
            #     f"Intercepted request: {method} {url} ({resource_type})"
            # )

            # Check if request should be intercepted
            if self._should_intercept(url, resource_type):
                self._blocked_count += 1
                logger.info(f"Blocked request: {url}")
                info.block(True)
                return

            # Add custom headers
            self._add_custom_headers(info)
            
        except Exception as e:
            logger.error(f"Error in request interceptor: {str(e)}")
    
    def _should_intercept(self, url: str, resource_type: str) -> bool:
        """Check if request should be intercepted"""
        # Check domain
        domain = QUrl(url).host()

        # Check if domain is in allowed list
        if self._allowed_domains and domain not in self._allowed_domains:
            return True

        # Check if domain is in blocked list
        if domain in self._blocked_domains:
            return True

        # Check resource type
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
        """Add custom headers"""
        for key, value in self._custom_headers.items():
            info.setHttpHeader(key.encode(), value.encode())

    def add_allowed_domain(self, domain: str):
        """Add allowed domain"""
        self._allowed_domains.add(domain)
        logger.info(f"Added allowed domain: {domain}")

    def add_blocked_domain(self, domain: str):
        """Add blocked domain"""
        self._blocked_domains.add(domain)
        logger.info(f"Added blocked domain: {domain}")

    def set_custom_header(self, key: str, value: str):
        """Set custom header"""
        self._custom_headers[key] = value
        logger.info(f"Set custom header: {key}: {value}")

    def clear_custom_headers(self):
        """Clear all custom headers"""
        self._custom_headers.clear()
        logger.info("Cleared all custom headers")

    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics information"""
        return {
            'total_requests': self._request_count,
            'blocked_requests': self._blocked_count,
            'allowed_domains': list(self._allowed_domains),
            'blocked_domains': list(self._blocked_domains),
            'custom_headers': self._custom_headers.copy()
        }

    def reset_statistics(self):
        """Reset statistics information"""
        self._request_count = 0
        self._blocked_count = 0
        logger.info("Reset request statistics")