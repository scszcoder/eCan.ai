"""
User Path Helper - Utility functions for getting user-specific paths.

This module provides centralized functions to get user-specific directory paths,
following the same logic as MainWindow to ensure consistency across the application.
"""

import os
from typing import Optional
from config import app_info


def get_log_user(user_email: Optional[str] = None) -> str:
    """
    Get sanitized log_user identifier from user email.
    
    This function follows the same logic as MainWindow.__init__ to generate
    a filesystem-safe user identifier from an email address.
    
    Args:
        user_email: User's email address (e.g., "249511118@qq.com")
                   If None, tries to get from app_context
    
    Returns:
        Sanitized user identifier (e.g., "249511118_qq_com")
    
    Examples:
        >>> get_log_user("249511118@qq.com")
        '249511118_qq_com'
        >>> get_log_user("user@example.com")
        'user_example_com'
    """
    # Try to get user from parameter first
    if not user_email:
        # Try to get from app_context (MainWindow instance)
        try:
            from app_context import AppContext
            main_window = AppContext.get_main_window()
            if main_window and hasattr(main_window, 'log_user'):
                return main_window.log_user
            if main_window and hasattr(main_window, 'user'):
                user_email = main_window.user
        except Exception:
            pass
    
    # If still no user, return a default
    if not user_email:
        return "default_user"
    
    # Sanitize email to filesystem-safe format (same logic as MainWindow)
    try:
        local_part, domain_part = user_email.split("@", 1)
    except ValueError:
        local_part, domain_part = user_email, "local"
    
    domain_part_sanitized = domain_part.replace(".", "_")
    log_user = f"{local_part}_{domain_part_sanitized}"
    
    return log_user


def get_user_data_dir(user_email: Optional[str] = None, subdir: Optional[str] = None) -> str:
    """
    Get user-specific data directory path.
    
    Args:
        user_email: User's email address. If None, tries to get from app_context
        subdir: Optional subdirectory under user data dir (e.g., "debug/workflows")
    
    Returns:
        Full path to user data directory
    
    Examples:
        >>> get_user_data_dir("249511118@qq.com")
        '/path/to/eCan.ai/249511118_qq_com'
        >>> get_user_data_dir("249511118@qq.com", "debug/workflows")
        '/path/to/eCan.ai/249511118_qq_com/debug/workflows'
    """
    log_user = get_log_user(user_email)
    
    # Get base data path from app_info singleton
    # app_info is the singleton instance, not the module
    from config.app_info import app_info as app_info_instance
    base_path = app_info_instance.appdata_path
    
    # Construct user data directory
    user_data_dir = os.path.join(base_path, log_user)
    
    # Add subdirectory if specified
    if subdir:
        user_data_dir = os.path.join(user_data_dir, subdir)
    
    return user_data_dir


def ensure_user_data_dir(user_email: Optional[str] = None, subdir: Optional[str] = None) -> str:
    """
    Get user-specific data directory path and ensure it exists.
    
    Args:
        user_email: User's email address. If None, tries to get from app_context
        subdir: Optional subdirectory under user data dir (e.g., "debug/workflows")
    
    Returns:
        Full path to user data directory (guaranteed to exist)
    
    Examples:
        >>> ensure_user_data_dir("249511118@qq.com", "debug/workflows")
        '/path/to/eCan.ai/249511118_qq_com/debug/workflows'
    """
    user_data_dir = get_user_data_dir(user_email, subdir)
    
    # Create directory if it doesn't exist
    os.makedirs(user_data_dir, exist_ok=True)
    
    return user_data_dir
