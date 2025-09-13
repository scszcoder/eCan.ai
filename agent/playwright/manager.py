#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Playwright Browser Manager
Implements lazy initialization and browser lifecycle management
"""

import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any
from threading import Lock

from .core import setup_playwright, core_utils
from .core.helpers import log_with_emoji, friendly_error_message
from app_context import AppContext

from utils.logger_helper import logger_helper as logger


class PlaywrightManager:
    """
    Playwright Browser Manager

    Features:
    - Lazy initialization: Initialize only when needed
    - Thread-safe: Support for multi-threaded environments
    - State management: Provides complete state information
    - Error handling: Graceful error handling and recovery
    """
    
    def __init__(self):
        self._initialized = False
        self._browsers_path: Optional[str] = None
        self._lock = Lock()
        self.ctx = AppContext()
        self._initialization_error: Optional[str] = None
        
        # Lazy initialization flag
        self._lazy_init_done = False
    
    def _ensure_initialized(self) -> bool:
        """
        Ensure Playwright is initialized (thread-safe)

        Returns:
            bool: Whether initialization was successful
        """
        with self._lock:
            if self._initialized:
                return True
            
            if self._initialization_error:
                logger.warning(f"Playwright initialization previously failed: {self._initialization_error}")
                return False
            
            try:
                logger.info("🚀 Initializing Playwright browsers...")

                # Print environment information
                self._print_environment_info()

                # Setup Playwright browser environment
                browsers_path = setup_playwright()

                if browsers_path and browsers_path.exists():
                    self._browsers_path = str(browsers_path)

                    # Set environment variables
                    core_utils.set_environment_variables(browsers_path)
                    log_with_emoji("success", f"Environment variables set successfully: {browsers_path}")

                    # Save Playwright path to AppContext
                    self.ctx.set_playwright_browsers_path(self._browsers_path)

                    self._initialized = True
                    logger.info(f"✅ Playwright browsers initialized successfully at: {browsers_path}")
                    return True
                else:
                    error_msg = "Invalid Playwright browsers path"
                    self._initialization_error = error_msg
                    logger.error(f"❌ {error_msg}")
                    return False

            except Exception as e:
                # Use simplified error handling
                error_msg = friendly_error_message(e, "manager_initialization")
                self._initialization_error = str(e)
                logger.error(f"❌ Playwright initialization failed: {error_msg}")
                return False
    
    def get_browsers_path(self) -> Optional[str]:
        """
        Get Playwright browsers path

        Returns:
            str: Browser path, or None if not initialized
        """
        if not self._ensure_initialized():
            return None
        return self._browsers_path
    
    def is_initialized(self) -> bool:
        """
        Check if initialized

        Returns:
            bool: Whether initialized
        """
        with self._lock:
            return self._initialized
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get current status information

        Returns:
            Dict: Dictionary containing status information
        """
        with self._lock:
            status = {
                "initialized": self._initialized,
                "browsers_path": self._browsers_path,
                "path_exists": Path(self._browsers_path).exists() if self._browsers_path else False,
                "initialization_error": self._initialization_error,
                "lazy_init_done": self._lazy_init_done
            }
            
            # Validate browser installation
            if self._browsers_path:
                status["browser_installation_valid"] = core_utils.validate_browser_installation(Path(self._browsers_path))
            else:
                status["browser_installation_valid"] = False
            
            return status
    
    def force_reinitialize(self) -> bool:
        """
        Force re-initialization (for error recovery)

        Returns:
            bool: Whether re-initialization was successful
        """
        with self._lock:
            # Clear previous state
            self._initialized = False
            self._browsers_path = None
            self._initialization_error = None

            # Re-initialize
            return self._ensure_initialized()
    
    def lazy_init(self) -> bool:
        """
        Lazy initialization (called on first use)

        Returns:
            bool: Whether initialization was successful
        """
        if self._lazy_init_done:
            return self._initialized
        
        self._lazy_init_done = True
        return self._ensure_initialized()
    
    def _print_environment_info(self) -> None:
        """Print Playwright environment information"""
        env_info = self.get_environment_info()

        logger.info("📋 Playwright Environment Information:")
        logger.info(f"  Platform: {env_info['platform']}")
        logger.info(f"  Frozen (PyInstaller): {env_info['frozen']}")

        if env_info['meipass']:
            logger.info(f"  MEI Pass: {env_info['meipass']}")

        logger.info(f"  Bundled Path: {env_info['bundled_path'] or 'None'}")
        logger.info(f"  Default Path: {env_info['default_path']}")
        logger.info(f"  App Data Path: {env_info['app_data_path']}")

        logger.info("  Environment Variables:")
        for var_name, var_value in env_info['env_variables'].items():
            if var_value:
                logger.info(f"    {var_name}: {var_value}")
            else:
                logger.info(f"    {var_name}: <not set>")

    def get_environment_info(self) -> Dict[str, Any]:
        """
        Get environment information

        Returns:
            Dict: Environment information dictionary
        """
        return {
            "platform": sys.platform,
            "frozen": getattr(sys, 'frozen', False),
            "meipass": getattr(sys, '_MEIPASS', None),
            "bundled_path": str(core_utils.get_bundled_path()) if core_utils.get_bundled_path() else None,
            "default_path": str(core_utils.get_default_browsers_path()),
            "app_data_path": str(core_utils.get_app_data_path()),
            "env_variables": {
                "PLAYWRIGHT_BROWSERS_PATH": os.getenv(core_utils.ENV_BROWSERS_PATH),
                "PLAYWRIGHT_CACHE_DIR": os.getenv(core_utils.ENV_CACHE_DIR),
                "PLAYWRIGHT_BROWSERS_PATH_OVERRIDE": os.getenv(core_utils.ENV_BROWSERS_PATH_OVERRIDE)
            }
        }
    
    def validate_installation(self) -> bool:
        """
        Validate if current installation is valid

        Returns:
            bool: Whether installation is valid
        """
        if not self._initialized:
            return False
        
        if not self._browsers_path:
            return False
        
        return core_utils.validate_browser_installation(Path(self._browsers_path))
    
    def cleanup(self):
        """
        Clean up resources (if needed)
        """
        with self._lock:
            # Clear environment variables
            core_utils.clear_environment_variables()

            # Reset state
            self._initialized = False
            self._browsers_path = None
            self._initialization_error = None
            self._lazy_init_done = False

            logger.info("Playwright manager cleaned up")


# Global manager instance
_manager_instance: Optional[PlaywrightManager] = None
_manager_lock = Lock()


def get_playwright_manager() -> PlaywrightManager:
    """
    Get global Playwright manager instance (singleton pattern)

    Returns:
        PlaywrightManager: Manager instance
    """
    global _manager_instance
    
    if _manager_instance is None:
        with _manager_lock:
            if _manager_instance is None:
                _manager_instance = PlaywrightManager()
    
    return _manager_instance


def initialize_playwright_lazy() -> bool:
    """
    Convenience function: Lazy initialize Playwright

    Returns:
        bool: Whether initialization was successful
    """
    return get_playwright_manager().lazy_init()


def get_playwright_status() -> Dict[str, Any]:
    """
    Convenience function: Get Playwright status

    Returns:
        Dict: Status information
    """
    return get_playwright_manager().get_status()
