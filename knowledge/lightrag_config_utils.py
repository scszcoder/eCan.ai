"""
LightRAG Configuration Utilities
Shared utilities for managing LightRAG configuration file paths
"""
import os
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger('eCan')


def get_user_env_path() -> Optional[Path]:
    """
    Get user-specific env file path from MainWindow.my_ecb_data_homepath
    
    Returns:
        Path to user's lightrag.env file, or None if unable to determine
    """
    try:
        from app_context import AppContext
        main_window = AppContext.get_main_window()
        if main_window and hasattr(main_window, 'my_ecb_data_homepath'):
            user_data_dir = Path(main_window.my_ecb_data_homepath)
            return user_data_dir / "resource" / "data" / "lightrag.env"
        else:
            logger.warning("Failed to get main_window or my_ecb_data_homepath")
            return None
    except Exception as e:
        logger.warning(f"Failed to get user env path: {e}")
        return None


def get_template_env_path() -> Optional[Path]:
    """
    Get template env file path from app home directory
    
    Returns:
        Path to lightrag_template.env file, or None if unable to determine
    """
    try:
        from config.app_info import app_info
        app_home_dir = Path(app_info.apphomepath)
        return app_home_dir / "resource" / "data" / "lightrag_template.env"
    except Exception as e:
        logger.warning(f"Failed to get template env path from app_info: {e}")
        # Fallback to script directory for development
        try:
            script_dir = Path(__file__).parent
            project_root = script_dir.parent
            return project_root / "resource" / "data" / "lightrag_template.env"
        except Exception as fallback_error:
            logger.error(f"Fallback template path also failed: {fallback_error}")
            return None


def ensure_user_env_file() -> Optional[Path]:
    """
    Ensure user env file exists, copy from template if not
    
    Returns:
        Path to user's lightrag.env file, or None if unable to create/access
    """
    user_env_path = get_user_env_path()
    if not user_env_path:
        logger.error("Failed to get user env path")
        return None
    
    # If user env file already exists, return it
    if user_env_path.exists():
        return user_env_path
    
    # Get template path
    template_path = get_template_env_path()
    if not template_path:
        logger.warning("Failed to get template env path")
        return user_env_path  # Return user path anyway, will be created on save
    
    if not template_path.exists():
        logger.warning(f"Template env file not found at: {template_path}")
        return user_env_path  # Return user path anyway, will be created on save
    
    # Copy template to user directory
    try:
        import shutil
        user_env_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(template_path, user_env_path)
        logger.info(f"Copied template env from {template_path} to {user_env_path}")
        return user_env_path
    except Exception as e:
        logger.error(f"Failed to copy template env file: {e}")
        return user_env_path  # Return user path anyway, will be created on save
