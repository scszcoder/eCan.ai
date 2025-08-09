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
    """获取用户友好的错误消息"""
    error_messages = {
        UpdateErrorCode.NETWORK_ERROR: "网络连接失败，请检查网络设置后重试",
        UpdateErrorCode.CONNECTION_TIMEOUT: "连接超时，请稍后重试",
        UpdateErrorCode.SERVER_UNAVAILABLE: "更新服务器暂时不可用，请稍后重试",
        UpdateErrorCode.SIGNATURE_VERIFICATION_FAILED: "更新包验证失败，可能存在安全风险",
        UpdateErrorCode.HASH_VERIFICATION_FAILED: "更新包完整性验证失败，请重新下载",
        UpdateErrorCode.PACKAGE_CORRUPTED: "更新包已损坏，请重新下载",
        UpdateErrorCode.PLATFORM_NOT_SUPPORTED: "当前平台不支持自动更新",
        UpdateErrorCode.FRAMEWORK_NOT_FOUND: "更新组件未找到，请重新安装应用程序",
        UpdateErrorCode.CLI_TOOL_NOT_FOUND: "更新工具未找到，请重新安装应用程序",
        UpdateErrorCode.PERMISSION_DENIED: "权限不足，请以管理员身份运行",
        UpdateErrorCode.INSUFFICIENT_SPACE: "磁盘空间不足，请清理后重试",
        UpdateErrorCode.INVALID_CONFIG: "配置文件无效，请重置配置",
        UpdateErrorCode.MISSING_PUBLIC_KEY: "安全密钥缺失，无法验证更新包",
        UpdateErrorCode.OPERATION_CANCELLED: "操作已取消",
        UpdateErrorCode.ALREADY_IN_PROGRESS: "更新操作正在进行中",
        UpdateErrorCode.UNKNOWN_ERROR: "发生未知错误，请联系技术支持"
    }
    
    return error_messages.get(error.code, error.message)


def create_error_from_exception(exc: Exception, context: str = "") -> UpdateError:
    """从标准异常创建UpdateError"""
    import requests
    
    if isinstance(exc, requests.exceptions.ConnectionError):
        return NetworkError(
            f"网络连接失败: {str(exc)}",
            {"context": context, "original_error": str(exc)}
        )
    elif isinstance(exc, requests.exceptions.Timeout):
        return UpdateError(
            UpdateErrorCode.CONNECTION_TIMEOUT,
            f"连接超时: {str(exc)}",
            {"context": context, "original_error": str(exc)}
        )
    elif isinstance(exc, FileNotFoundError):
        return PlatformError(
            UpdateErrorCode.CLI_TOOL_NOT_FOUND,
            f"文件未找到: {str(exc)}",
            {"context": context, "original_error": str(exc)}
        )
    elif isinstance(exc, PermissionError):
        return PermissionError(
            f"权限不足: {str(exc)}",
            {"context": context, "original_error": str(exc)}
        )
    else:
        return UpdateError(
            UpdateErrorCode.UNKNOWN_ERROR,
            f"未知错误: {str(exc)}",
            {"context": context, "original_error": str(exc)}
        )
