"""
OTA update error handling module
Defines various update-related exceptions and error handling mechanisms
"""

import os
import sys
from enum import Enum
from pathlib import Path
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


# ---------------------------------------------------------------------------
# Path / permission helpers
#
# These live here (and NOT in ``installer.py``) because:
#
#   * ``installer.py`` imports ``ota.i18n`` at module-load time so it
#     can format translated progress strings. ``ota.i18n`` itself is
#     pure Python (translation tables only, no PySide6), so importing
#     it is cheap. The original location ``ota.gui.i18n`` had to be
#     moved out of the GUI package because importing it would trigger
#     ``ota.gui.__init__`` → ``ota.gui.dialog`` → PySide6, which made
#     the whole ``ota.core`` tree unloadable from lightweight CI
#     runners. See Bug #6 in the installer.py history.
#   * ``errors.py`` is a leaf module (only stdlib + enum + Path), so
#     importing ``safe_makedirs`` / ``is_writable_dir`` from here is
#     safe from any test that needs the OTA core without the GUI stack.
# ---------------------------------------------------------------------------


def safe_makedirs(path: Path, *, purpose: str = "") -> Path:
    """Create ``path`` (and parents) like ``mkdir(parents=True, exist_ok=True)``.

    The stock ``mkdir`` raises ``PermissionError`` with no hint about
    why the directory couldn't be created. In an OTA flow that ends
    up calling the installer (which itself wants to write to
    ``<appdata>``), a bare ``PermissionError`` looks like an installer
    bug to the user — they don't know whether to clear ACLs, fix
    ownership, free up disk space, or just retry. This wrapper:

      * Catches ``PermissionError`` and re-raises as a
        ``RuntimeError`` with a platform-specific remediation hint
        (the user is told to check ACLs / ownership / disk space).
      * Catches ``FileExistsError`` (path exists as a regular file
        with the same name) and re-raises as ``RuntimeError`` —
        ``mkdir(exist_ok=True)`` does NOT suppress this one.
      * Catches ``OSError`` for everything else (disk full, path
        too long, …) and re-raises with the ``errno`` text so the
        caller logs enough detail to debug.

    Args:
        path: Directory to create.
        purpose: Human-readable role for this directory
            (e.g. ``"OTA scripts"``, ``"OTA downloads"``). Used in
            the error message so the GUI / log makes it obvious
            which directory the failure belongs to.

    Returns:
        The same ``path`` for fluent use.

    Raises:
        RuntimeError: with actionable remediation guidance.
    """
    path = Path(path)
    try:
        path.mkdir(parents=True, exist_ok=True)
        return path
    except PermissionError as e:
        hint = ""
        if sys.platform == "win32":
            hint = (
                "On Windows this is usually a folder ACL or anti-virus "
                "quarantine. Check the folder's Security tab and make sure "
                "your user has 'Modify' permission; if an anti-virus is "
                "involved, exclude this folder and retry."
            )
        elif sys.platform == "darwin":
            hint = (
                "On macOS this is usually a Folder Permission in System "
                "Settings -> Privacy & Security -> Files and Folders, or "
                "a company MDM profile. Try moving the app out of the "
                "affected location or contact your IT admin."
            )
        else:
            hint = (
                "On Linux check that your user owns the parent directory "
                "(``ls -ld <path>``) and that the filesystem is not "
                "mounted read-only."
            )
        raise RuntimeError(
            f"OTA cannot create the {purpose or 'OTA'} directory "
            f"{path}: permission denied. {hint}"
        ) from e
    except FileExistsError as e:
        raise RuntimeError(
            f"OTA cannot create the {purpose or 'OTA'} directory "
            f"{path}: a regular file with that name already exists. "
            f"Remove or rename the conflicting file and retry."
        ) from e
    except OSError as e:
        raise RuntimeError(
            f"OTA cannot create the {purpose or 'OTA'} directory "
            f"{path}: {e.strerror or e} (errno={getattr(e, 'errno', '?')}). "
            f"Check available disk space and that the path is not too long."
        ) from e


def is_writable_dir(path: Path) -> bool:
    """Return True if ``path`` exists and is writable by the current user.

    Used before launching the installer to fail fast with a clear error
    if the install directory is on a read-only mount or otherwise
    inaccessible. Pure existence (``os.path.exists``) is not enough —
    a ``/Applications`` install on macOS reports ``True`` for
    ``os.path.exists`` but ``False`` for ``os.access(..., W_OK)``
    without sudo.
    """
    try:
        path = Path(path)
        if not path.exists():
            return False
        return os.access(str(path), os.W_OK)
    except Exception:
        return False
