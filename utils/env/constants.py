"""
Environment Variable Constants

This module contains all constants related to environment variable management.
"""

from typing import List, Dict

# Environment variable loading constants
class EnvLoadingConstants:
    """Constants for environment variable loading"""
    
    # Marker to track if shell environment has been loaded
    SHELL_ENV_LOADED_MARKER = '_ECAN_SHELL_ENV_LOADED'
    
    # Timeout for shell command execution (seconds)
    SHELL_COMMAND_TIMEOUT = 5
    
    # Maximum number of environment variables to load at once
    MAX_ENV_VARS_TO_LOAD = 1000

# Shell configuration constants
class ShellConfigConstants:
    """Constants for shell configuration files"""
    
    # Shell configuration files by shell type
    ZSH_CONFIG_FILES = ['~/.zshrc', '~/.zprofile', '~/.zshenv']
    BASH_CONFIG_FILES = ['~/.bash_profile', '~/.bashrc', '~/.profile']
    
    # All possible configuration files
    ALL_CONFIG_FILES = [
        '~/.zshrc', '~/.zprofile', '~/.zshenv', '~/.zlogin',
        '~/.bash_profile', '~/.bashrc', '~/.profile', '~/.bash_login',
        '~/.env', '~/.environment'
    ]
    
    # Shell commands
    ZSH_COMMAND = 'zsh'
    BASH_COMMAND = 'bash'
    
    # Default shell paths
    DEFAULT_ZSH_PATH = '/bin/zsh'
    DEFAULT_BASH_PATH = '/bin/bash'

# Environment detection constants
class EnvDetectionConstants:
    """Constants for environment detection"""
    
    # Terminal environment indicators
    TERMINAL_INDICATORS = ['TERM', 'SHELL', 'PS1']
    
    # IDE environment indicators
    IDE_INDICATORS = [
        'PYCHARM_HOSTED',
        'VSCODE_PID', 
        'VSCODE_INJECTION',
        'WINDSURF_PID',
        'JUPYTER_RUNTIME_DIR'
    ]
    
    # PyInstaller indicators
    PYINSTALLER_INDICATORS = ['frozen']  # sys.frozen attribute

# API key patterns and validation constants
class APIKeyConstants:
    """Constants for API key management"""
    
    # API key patterns for identification
    API_KEY_SUFFIXES = ['_API_KEY', '_KEY', '_TOKEN', '_SECRET', '_PASSWORD']
    
    # Special environment variables that are considered sensitive
    SPECIAL_SENSITIVE_VARS = ['AZURE_ENDPOINT', 'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY']
    
    # Known orphaned variables to clean up
    ORPHANED_PATTERNS = ['VSCODE_DEBUGPY_ADAPTER_ENDPOINTS']
    
    # Minimum lengths for different validation levels
    MIN_API_KEY_LENGTH = 10
    MIN_SECURE_API_KEY_LENGTH = 20
    
    # Masking configuration
    MASK_PREFIX_CHARS = 8
    MASK_SUFFIX_CHARS = 4
    MASK_MIN_LENGTH = 12
    MASK_FALLBACK_PREFIX = 4

# System platform constants
class PlatformConstants:
    """Constants for different platforms"""
    
    MACOS = 'Darwin'
    WINDOWS = 'Windows'
    LINUX = 'Linux'
    
    # Platform-specific commands
    MACOS_SHELL_DETECTION = ['zsh', 'bash']
    WINDOWS_ENV_COMMAND = 'reg query "HKEY_CURRENT_USER\\Environment" /s'
    
    # Registry patterns for Windows
    WINDOWS_REG_PATTERNS = ['REG_SZ', 'REG_EXPAND_SZ']

# Logging constants
class LoggingConstants:
    """Constants for logging messages"""
    
    # Emoji prefixes for different log types
    EMOJI_START = '🚀'
    EMOJI_SUCCESS = '✅'
    EMOJI_WARNING = '⚠️'
    EMOJI_ERROR = '❌'
    EMOJI_INFO = 'ℹ️'
    EMOJI_DELETE = '🗑️'
    EMOJI_SEARCH = '🔍'
    EMOJI_TARGET = '🎯'
    EMOJI_KEY = '🔑'
    EMOJI_CLEAN = '🧹'
    
    # Log message templates
    DELETION_START_MSG = f"{EMOJI_DELETE} Starting deletion process for {{env_var}}"
    DELETION_SUCCESS_MSG = f"{EMOJI_SUCCESS} {{env_var}} successfully removed from environment"
    DELETION_WARNING_MSG = f"{EMOJI_WARNING} {{env_var}} still exists in environment after deletion"
    CLEANUP_START_MSG = f"{EMOJI_CLEAN} Cleaning up deleted API keys on {{system}}"
    
# File operation constants
class FileConstants:
    """Constants for file operations"""
    
    # File encoding
    DEFAULT_ENCODING = 'utf-8'
    
    # File operation timeouts
    FILE_READ_TIMEOUT = 5
    FILE_WRITE_TIMEOUT = 10
    
    # Backup file suffix
    BACKUP_SUFFIX = '.bak'
    
    # Line endings
    UNIX_LINE_ENDING = '\n'
    WINDOWS_LINE_ENDING = '\r\n'

# Error handling constants
class ErrorConstants:
    """Constants for error handling"""
    
    # Error messages
    CONFIG_FILE_NOT_FOUND = "Configuration file not found: {path}"
    INVALID_API_KEY_FORMAT = "Invalid API key format for {env_var}"
    SHELL_COMMAND_FAILED = "Shell command failed: {command}"
    PERMISSION_DENIED = "Permission denied accessing: {path}"
    
    # Error codes
    SUCCESS = 0
    CONFIG_ERROR = 1
    PERMISSION_ERROR = 2
    VALIDATION_ERROR = 3
    SYSTEM_ERROR = 4

# Default values
class DefaultValues:
    """Default values for various operations"""
    
    # Default shell if detection fails
    DEFAULT_SHELL = '/bin/zsh'
    
    # Default timeout values
    DEFAULT_TIMEOUT = 5
    DEFAULT_RETRY_COUNT = 3
    
    # Default batch sizes
    DEFAULT_BATCH_SIZE = 100
    DEFAULT_MAX_ITEMS = 1000
