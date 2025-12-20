"""
Environment Variables Management Package

This package provides utilities and constants for managing environment variables
across different platforms and shell configurations.
"""

from .constants import (
    EnvLoadingConstants,
    ShellConfigConstants,
    EnvDetectionConstants,
    APIKeyConstants,
    PlatformConstants,
    LoggingConstants,
    FileConstants,
    ErrorConstants,
    DefaultValues
)

from .env_utils import (
    EnvironmentLoader,
    load_shell_environment,
    get_api_keys_status,
    is_shell_environment_loaded
)

__all__ = [
    # Constants
    'EnvLoadingConstants',
    'ShellConfigConstants', 
    'EnvDetectionConstants',
    'APIKeyConstants',
    'PlatformConstants',
    'LoggingConstants',
    'FileConstants',
    'ErrorConstants',
    'DefaultValues',
    
    # Utilities
    'EnvironmentLoader',
    'load_shell_environment',
    'get_api_keys_status',
    'is_shell_environment_loaded'
]
