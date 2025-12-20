"""
OTA update error handling module
Defines various update-related exceptions and error handling mechanisms
"""

from enum import Enum
from typing import Optional, Dict, Any


class UpdateErrorCode(Enum):
    """Update error codes"""
    # Network related errors
    NETWORK_ERROR = "NETWORK_ERROR"
    CONNECTION_TIMEOUT = "CONNECTION_TIMEOUT"
    SERVER_UNAVAILABLE = "SERVER_UNAVAILABLE"
    
    # Verification related errors
    SIGNATURE_VERIFICATION_FAILED = "SIGNATURE_VERIFICATION_FAILED"
    HASH_VERIFICATION_FAILED = "HASH_VERIFICATION_FAILED"
    PACKAGE_CORRUPTED = "PACKAGE_CORRUPTED"
    
    # Platform related errors
    PLATFORM_NOT_SUPPORTED = "PLATFORM_NOT_SUPPORTED"
    FRAMEWORK_NOT_FOUND = "FRAMEWORK_NOT_FOUND"
    CLI_TOOL_NOT_FOUND = "CLI_TOOL_NOT_FOUND"
    
    # Permission related errors
    PERMISSION_DENIED = "PERMISSION_DENIED"
    INSUFFICIENT_SPACE = "INSUFFICIENT_SPACE"
    
    # Configuration related errors
    INVALID_CONFIG = "INVALID_CONFIG"
    MISSING_PUBLIC_KEY = "MISSING_PUBLIC_KEY"
    
    # Generic errors
    UNKNOWN_ERROR = "UNKNOWN_ERROR"
    OPERATION_CANCELLED = "OPERATION_CANCELLED"
    ALREADY_IN_PROGRESS = "ALREADY_IN_PROGRESS"


class UpdateError(Exception):
    """Base class for update-related exceptions"""
    
    def __init__(self, code: UpdateErrorCode, message: str, details: Optional[Dict[str, Any]] = None):
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(f"[{code.value}] {message}")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format"""
        return {
            "code": self.code.value,
            "message": self.message,
            "details": self.details
        }


class NetworkError(UpdateError):
    """Network related error"""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(UpdateErrorCode.NETWORK_ERROR, message, details)


class VerificationError(UpdateError):
    """Verification related error"""
    
    def __init__(self, code: UpdateErrorCode, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(code, message, details)


class PlatformError(UpdateError):
    """Platform related error"""
    
    def __init__(self, code: UpdateErrorCode, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(code, message, details)


class PermissionError(UpdateError):
    """Permission related error"""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(UpdateErrorCode.PERMISSION_DENIED, message, details)


class ConfigError(UpdateError):
    """Configuration related error"""
    
    def __init__(self, code: UpdateErrorCode, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(code, message, details)


def get_user_friendly_message(error: UpdateError) -> str:
    """Get user-friendly error message (simplified version)"""
    error_messages = {
        UpdateErrorCode.NETWORK_ERROR: "Network connection failed",
        UpdateErrorCode.CONNECTION_TIMEOUT: "Connection timeout",
        UpdateErrorCode.SERVER_UNAVAILABLE: "Update server unavailable",
        UpdateErrorCode.SIGNATURE_VERIFICATION_FAILED: "Update package verification failed",
        UpdateErrorCode.HASH_VERIFICATION_FAILED: "Update package integrity verification failed",
        UpdateErrorCode.PACKAGE_CORRUPTED: "Update package corrupted",
        UpdateErrorCode.PLATFORM_NOT_SUPPORTED: "Platform not supported",
        UpdateErrorCode.FRAMEWORK_NOT_FOUND: "Update component not found",
        UpdateErrorCode.CLI_TOOL_NOT_FOUND: "Update tool not found",
        UpdateErrorCode.PERMISSION_DENIED: "Insufficient permissions",
        UpdateErrorCode.INSUFFICIENT_SPACE: "Insufficient disk space",
        UpdateErrorCode.INVALID_CONFIG: "Invalid configuration",
        UpdateErrorCode.MISSING_PUBLIC_KEY: "Security key missing",
        UpdateErrorCode.OPERATION_CANCELLED: "Operation cancelled",
        UpdateErrorCode.ALREADY_IN_PROGRESS: "Operation in progress",
        UpdateErrorCode.UNKNOWN_ERROR: "Unknown error"
    }
    
    return error_messages.get(error.code, error.message)


def create_error_from_exception(exc: Exception, context: str = "") -> UpdateError:
    """Create UpdateError from standard exception"""
    import requests
    import builtins as _bi
    
    # Add more detailed error information
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

# Simplified version: removed complex helper functions
def should_retry_error(error: UpdateError) -> bool:
    """Determine if error can be retried"""
    retryable_codes = {
        UpdateErrorCode.NETWORK_ERROR,
        UpdateErrorCode.CONNECTION_TIMEOUT,
        UpdateErrorCode.SERVER_UNAVAILABLE
    }
    return error.code in retryable_codes
