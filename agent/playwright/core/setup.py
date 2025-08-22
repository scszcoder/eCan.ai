#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Playwright 运行时设置模块
处理应用运行时的 Playwright 浏览器初始化和设置
"""

import sys
import os
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

from .utils import core_utils

from utils.logger_helper import logger_helper as logger


def _default_app_data_root() -> Path:
    """Get the default application data root directory for the current platform."""
    return core_utils.get_app_data_path()


def _validate_browser_installation(browsers_path: Path) -> bool:
    """Validate that the browser installation is complete and usable."""
    return core_utils.validate_browser_installation(browsers_path)


def _get_browser_info(browsers_path: Path) -> Dict[str, Any]:
    """Get information about installed browsers."""
    info = {
        'path': str(browsers_path),
        'browsers': [],
        'total_size': 0,
        'last_updated': None
    }
    
    try:
        # Get browser directories
        browser_dirs = [d for d in browsers_path.iterdir() 
                       if d.is_dir() and not d.name.startswith('.')]
        
        for browser_dir in browser_dirs:
            browser_info = {
                'name': browser_dir.name,
                'size': sum(f.stat().st_size for f in browser_dir.rglob('*') if f.is_file()),
                'files': len(list(browser_dir.rglob('*')))
            }
            info['browsers'].append(browser_info)
            info['total_size'] += browser_info['size']
        
        # Get last modification time
        if browsers_path.exists():
            info['last_updated'] = datetime.fromtimestamp(browsers_path.stat().st_mtime).isoformat()
            
    except Exception as e:
        logger.error(f"Error getting browser info: {e}")
    
    return info


def ensure_playwright_browsers_ready(app_data_root: Optional[Path] = None,
                                   force_refresh: bool = False) -> Path:
    """Ensure Playwright browsers are available at a writable path and set env.

    This function ensures that Playwright browsers are available at a writable
    location and sets the necessary environment variables.

    Args:
        app_data_root: Optional path to app data directory. If None, uses default.
        force_refresh: If True, force refresh the browser installation.

    Returns:
        Path to the directory containing Playwright browsers.

    The function follows this logic:
    - Frozen runtime: <_MEIPASS>/third_party/ms-playwright
    - Dev runtime: <repo>/third_party/ms-playwright
    - If found, copy to <app_data_root>/ms-playwright when missing or incomplete.
    - Finally set PLAYWRIGHT_BROWSERS_PATH to the writable directory and return it.
    """
    # PyInstaller 特殊处理：直接使用打包的浏览器
    if getattr(sys, 'frozen', False):
        bundled_path = Path(sys._MEIPASS) / 'third_party' / 'ms-playwright'
        if bundled_path.exists() and _validate_browser_installation(bundled_path):
            logger.info(f"Using bundled Playwright browsers in PyInstaller: {bundled_path}")
            core_utils.set_environment_variables(bundled_path)
            return bundled_path
        else:
            logger.warning(f"Bundled browsers not found or invalid at: {bundled_path}")

    # 检查是否已经设置了有效的环境变量
    existing_path = core_utils.get_environment_browsers_path()
    if existing_path and not force_refresh:
        if _validate_browser_installation(existing_path):
            logger.info(f"Using existing PLAYWRIGHT_BROWSERS_PATH: {existing_path}")
            return existing_path
    
    # 简化：不再从配置文件读取路径，避免过度实现
    
    if app_data_root is None:
        app_data_root = _default_app_data_root()
    
    logger.info(f"Setting up Playwright browsers in: {app_data_root}")
    
    # Target directory in app data
    target = app_data_root / 'ms-playwright'
    
    # 首先清理任何不完整的浏览器目录
    if target.exists():
        core_utils.cleanup_incomplete_browsers(target)

    # 然后检查目标目录是否已经有效
    if not force_refresh and _validate_browser_installation(target):
        logger.info("Browser installation already exists and is valid")
        core_utils.set_environment_variables(target)
        logger.info(f"Set PLAYWRIGHT_BROWSERS_PATH to: {target}")
        return target
    
    # 检查是否有现有的 Playwright 缓存可以使用
    existing_cache = core_utils.find_playwright_cache()
    if existing_cache and existing_cache != target and not force_refresh:
        logger.info(f"Found existing Playwright cache at: {existing_cache}")
        # 清理现有缓存中的不完整目录
        core_utils.cleanup_incomplete_browsers(existing_cache)
        if _validate_browser_installation(existing_cache):
            logger.info("Using existing valid browser installation")
            # 使用专用的复制函数来确保 browsers.json 正确处理
            try:
                core_utils.copy_playwright_browsers(existing_cache, target)
                logger.info(f"Copied existing browsers to: {target}")
                core_utils.set_environment_variables(target)
                logger.info(f"Set PLAYWRIGHT_BROWSERS_PATH to: {target}")
                return target
            except Exception as e:
                logger.warning(f"Failed to copy existing browsers: {e}")
                # 继续使用原有逻辑
    
    # 在开发环境中，检查是否有本地的 third_party 目录
    if not getattr(sys, 'frozen', False):
        local_third_party = Path.cwd() / 'third_party' / 'ms-playwright'
        if local_third_party.exists() and _validate_browser_installation(local_third_party):
            logger.info(f"Found valid local third_party browsers at: {local_third_party}")
            # 确保复制到应用内部目录，而不是直接使用本地目录
            try:
                core_utils.copy_playwright_browsers(local_third_party, target)
                logger.info(f"Copied local third_party browsers to: {target}")
                core_utils.set_environment_variables(target)
                logger.info(f"Set PLAYWRIGHT_BROWSERS_PATH to: {target}")
                return target
            except Exception as e:
                logger.warning(f"Failed to copy local third_party browsers: {e}")
                # 继续使用原有逻辑
    
    # Determine base directory for bundled browsers
    if getattr(sys, 'frozen', False):
        # PyInstaller frozen environment
        base_dir = Path(sys._MEIPASS)
        bundled = base_dir / 'third_party' / 'ms-playwright'
    else:
        # Development environment
        bundled = Path.cwd() / 'third_party' / 'ms-playwright'
    
    # Determine if we need to copy browsers
    should_copy = force_refresh or not _validate_browser_installation(target)
    
    if should_copy and bundled.exists():
        logger.info(f"Copying bundled browsers from {bundled} to {target}")
        try:
            core_utils.copy_playwright_browsers(bundled, target)
            logger.info("Successfully copied bundled browsers")
            if _validate_browser_installation(target):
                core_utils.set_environment_variables(target)
                logger.info(f"Set PLAYWRIGHT_BROWSERS_PATH to: {target}")
                return target
        except Exception as e:
            logger.error(f"Failed to copy bundled browsers: {e}")
            # Fall back to runtime installation
            should_copy = True
    
    if should_copy:
        logger.info("No bundled browsers available for copying, attempting runtime installation.")
        try:
            core_utils.install_playwright_browsers(target)
            if _validate_browser_installation(target):
                logger.info("Installed Playwright browsers at runtime")
            else:
                logger.warning("Runtime installation did not produce a valid installation")
        except Exception as e:
            logger.error(f"Runtime installation of Playwright browsers failed: {e}")
            raise
    else:
        logger.info("Browser installation already exists and is valid")
    
    # Set environment for Playwright - CRITICAL for custom path
    core_utils.set_environment_variables(target)
    
    logger.info(f"Set PLAYWRIGHT_BROWSERS_PATH to: {target}")
    return target


def cleanup_playwright_browsers(app_data_root: Optional[Path] = None) -> bool:
    """Clean up Playwright browser installation.
    
    Args:
        app_data_root: Optional path to app data directory. If None, uses default.
        
    Returns:
        True if cleanup was successful, False otherwise.
    """
    try:
        if app_data_root is None:
            app_data_root = _default_app_data_root()
        
        browsers_path = app_data_root / 'ms-playwright'
        
        if browsers_path.exists():
            import shutil
            shutil.rmtree(browsers_path)
            logger.info(f"Cleaned up Playwright browsers at: {browsers_path}")
        
        # Clear environment variables
        if 'PLAYWRIGHT_BROWSERS_PATH' in os.environ:
            del os.environ['PLAYWRIGHT_BROWSERS_PATH']
            logger.info("Cleared PLAYWRIGHT_BROWSERS_PATH environment variable")
        
        return True
        
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")
        return False


def get_playwright_browsers_path() -> Optional[str]:
    """Get the current PLAYWRIGHT_BROWSERS_PATH environment variable value."""
    return core_utils.get_environment_browsers_path()


def is_playwright_ready() -> bool:
    """Check if Playwright browsers are ready and accessible."""
    browsers_path = get_playwright_browsers_path()
    if not browsers_path:
        return False
    
    return _validate_browser_installation(Path(browsers_path))


# 配置持久化与路径覆盖逻辑已移除，避免过度实现，保持初始化流程简单明了


def setup_playwright(app_data_root: Optional[Path] = None) -> Path:
    """Quick setup function that ensures Playwright is ready.
    
    This is a convenience function that calls ensure_playwright_browsers_ready()
    with default settings.
    """
    return ensure_playwright_browsers_ready(app_data_root)
