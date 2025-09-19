"""
OTA更新错误处理模块
定义各种更新相关的异常和错误处理机制
"""

from enum import Enum
from typing import Optional, Dict, Any


class UpdateErrorCode(Enum):
    """更新错误代码"""
    # 网络相关错误
    NETWORK_ERROR = "NETWORK_ERROR"
    CONNECTION_TIMEOUT = "CONNECTION_TIMEOUT"
    SERVER_UNAVAILABLE = "SERVER_UNAVAILABLE"
    
    # 验证相关错误
    SIGNATURE_VERIFICATION_FAILED = "SIGNATURE_VERIFICATION_FAILED"
    HASH_VERIFICATION_FAILED = "HASH_VERIFICATION_FAILED"
    PACKAGE_CORRUPTED = "PACKAGE_CORRUPTED"
    
    # 平台相关错误
    PLATFORM_NOT_SUPPORTED = "PLATFORM_NOT_SUPPORTED"
    FRAMEWORK_NOT_FOUND = "FRAMEWORK_NOT_FOUND"
    CLI_TOOL_NOT_FOUND = "CLI_TOOL_NOT_FOUND"
    
    # 权限相关错误
    PERMISSION_DENIED = "PERMISSION_DENIED"
    INSUFFICIENT_SPACE = "INSUFFICIENT_SPACE"
    
    # 配置相关错误
    INVALID_CONFIG = "INVALID_CONFIG"
    MISSING_PUBLIC_KEY = "MISSING_PUBLIC_KEY"
    
    # 通用错误
    UNKNOWN_ERROR = "UNKNOWN_ERROR"
    OPERATION_CANCELLED = "OPERATION_CANCELLED"
    ALREADY_IN_PROGRESS = "ALREADY_IN_PROGRESS"


class UpdateError(Exception):
    """更新相关异常基类"""
    
    def __init__(self, code: UpdateErrorCode, message: str, details: Optional[Dict[str, Any]] = None):
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(f"[{code.value}] {message}")
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "code": self.code.value,
            "message": self.message,
            "details": self.details
        }


class NetworkError(UpdateError):
    """网络相关错误"""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(UpdateErrorCode.NETWORK_ERROR, message, details)


class VerificationError(UpdateError):
    """验证相关错误"""
    
    def __init__(self, code: UpdateErrorCode, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(code, message, details)


class PlatformError(UpdateError):
    """平台相关错误"""
    
    def __init__(self, code: UpdateErrorCode, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(code, message, details)


class PermissionError(UpdateError):
    """权限相关错误"""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(UpdateErrorCode.PERMISSION_DENIED, message, details)


class ConfigError(UpdateError):
    """配置相关错误"""
    
    def __init__(self, code: UpdateErrorCode, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(code, message, details)


def get_user_friendly_message(error: UpdateError) -> str:
    """获取用户友好的错误消息（简化版）"""
    error_messages = {
        UpdateErrorCode.NETWORK_ERROR: "网络连接失败",
        UpdateErrorCode.CONNECTION_TIMEOUT: "连接超时",
        UpdateErrorCode.SERVER_UNAVAILABLE: "更新服务器不可用",
        UpdateErrorCode.SIGNATURE_VERIFICATION_FAILED: "更新包验证失败",
        UpdateErrorCode.HASH_VERIFICATION_FAILED: "更新包完整性验证失败",
        UpdateErrorCode.PACKAGE_CORRUPTED: "更新包已损坏",
        UpdateErrorCode.PLATFORM_NOT_SUPPORTED: "平台不支持",
        UpdateErrorCode.FRAMEWORK_NOT_FOUND: "更新组件未找到",
        UpdateErrorCode.CLI_TOOL_NOT_FOUND: "更新工具未找到",
        UpdateErrorCode.PERMISSION_DENIED: "权限不足",
        UpdateErrorCode.INSUFFICIENT_SPACE: "磁盘空间不足",
        UpdateErrorCode.INVALID_CONFIG: "配置无效",
        UpdateErrorCode.MISSING_PUBLIC_KEY: "安全密钥缺失",
        UpdateErrorCode.OPERATION_CANCELLED: "操作已取消",
        UpdateErrorCode.ALREADY_IN_PROGRESS: "操作正在进行中",
        UpdateErrorCode.UNKNOWN_ERROR: "未知错误"
    }
    
    return error_messages.get(error.code, error.message)


def create_error_from_exception(exc: Exception, context: str = "") -> UpdateError:
    """从标准异常创建UpdateError"""
    import requests
    import builtins as _bi
    
    # 添加更详细的错误信息
    error_details = {
        "context": context,
        "original_error": str(exc),
        "error_type": type(exc).__name__
    }
    
    if isinstance(exc, requests.exceptions.ConnectionError):
        return NetworkError(
            f"Network connection failed in {context}: {str(exc)}",
            error_details
        )
    elif isinstance(exc, requests.exceptions.Timeout):
        return UpdateError(
            UpdateErrorCode.CONNECTION_TIMEOUT,
            f"Connection timeout in {context}: {str(exc)}",
            error_details
        )
    elif isinstance(exc, requests.exceptions.HTTPError):
        status_code = getattr(exc.response, 'status_code', 'unknown')
        error_details["status_code"] = status_code
        return UpdateError(
            UpdateErrorCode.SERVER_UNAVAILABLE,
            f"HTTP error {status_code} in {context}: {str(exc)}",
            error_details
        )
    elif isinstance(exc, FileNotFoundError):
        return PlatformError(
            UpdateErrorCode.CLI_TOOL_NOT_FOUND,
            f"File not found in {context}: {str(exc)}",
            error_details
        )
    elif isinstance(exc, _bi.PermissionError):
        return PermissionError(
            f"Permission denied in {context}: {str(exc)}",
            error_details
        )
    elif isinstance(exc, OSError):
        return UpdateError(
            UpdateErrorCode.INSUFFICIENT_SPACE if "No space left" in str(exc) else UpdateErrorCode.UNKNOWN_ERROR,
            f"OS error in {context}: {str(exc)}",
            error_details
        )
    elif isinstance(exc, ValueError):
        return ConfigError(
            UpdateErrorCode.INVALID_CONFIG,
            f"Invalid value in {context}: {str(exc)}",
            error_details
        )
    else:
        return UpdateError(
            UpdateErrorCode.UNKNOWN_ERROR,
            f"Unexpected error in {context}: {str(exc)}",
            error_details
        )

# 简化版本：移除了复杂的辅助函数
def should_retry_error(error: UpdateError) -> bool:
    """判断错误是否可以重试"""
    retryable_codes = {
        UpdateErrorCode.NETWORK_ERROR,
        UpdateErrorCode.CONNECTION_TIMEOUT,
        UpdateErrorCode.SERVER_UNAVAILABLE
    }
    return error.code in retryable_codes
