"""
Icon Manager - Centralized icon management for the application
Solves the window flashing issue by ensuring icons are set only once at the right time.
"""

import os
import sys
from typing import Optional
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon


class IconManager:
    """
    Singleton icon manager to prevent duplicate icon setting operations.
    
    Design principles:
    1. Single responsibility: Only this class manages application icons
    2. State management: Track whether icons have been set
    3. Lazy initialization: Set icons only when window is ready
    4. No retries: Set once at the right time, not multiple attempts
    """
    
    _instance: Optional['IconManager'] = None
    _initialized: bool = False
    _icon_set: bool = False
    _taskbar_icon_set: bool = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        # Only initialize once
        if IconManager._initialized:
            return
        IconManager._initialized = True
        
        self.logger = None
        self.icon_path: Optional[str] = None
        self._find_icon_path()
    
    def set_logger(self, logger):
        """Set logger for debugging"""
        self.logger = logger
    
    def _log(self, message: str, level: str = 'info'):
        """Internal logging helper"""
        if self.logger:
            if level == 'debug':
                self.logger.debug(f"[IconManager] {message}")
            elif level == 'warning':
                self.logger.warning(f"[IconManager] {message}")
            elif level == 'error':
                self.logger.error(f"[IconManager] {message}")
            else:
                self.logger.info(f"[IconManager] {message}")
    
    def _find_icon_path(self) -> Optional[str]:
        """Find the application icon file"""
        try:
            from config.app_info import app_info
            resource_path = app_info.app_resources_path
            
            # Icon candidates in priority order
            candidates = [
                os.path.join(os.path.dirname(resource_path), "eCan.ico"),
                os.path.join(resource_path, "images", "logos", "icon_multi.ico"),
                os.path.join(resource_path, "images", "logos", "desktop_256x256.png"),
            ]
            
            for candidate in candidates:
                if os.path.exists(candidate):
                    self.icon_path = candidate
                    return candidate
            
            return None
        except Exception as e:
            if self.logger:
                self.logger.error(f"[IconManager] Failed to find icon: {e}")
            return None
    
    def set_application_icon(self, app: QApplication) -> bool:
        """
        Set Qt application icon (affects all windows by default).
        Should be called early in application startup.
        
        Returns:
            bool: True if successful, False otherwise
        """
        if IconManager._icon_set:
            self._log("Application icon already set, skipping", 'debug')
            return True
        
        if not self.icon_path:
            self._log("No icon path available", 'warning')
            return False
        
        try:
            app_icon = QIcon(self.icon_path)
            app.setWindowIcon(app_icon)
            IconManager._icon_set = True
            self._log(f"Application icon set: {self.icon_path}")
            return True
        except Exception as e:
            self._log(f"Failed to set application icon: {e}", 'error')
            return False
    
    def set_window_taskbar_icon(self, window, app: Optional[QApplication] = None) -> bool:
        """
        Set Windows taskbar icon for a specific window.
        Should be called ONCE after the window is fully visible.
        
        Args:
            window: The QMainWindow instance
            app: Optional QApplication instance (will get from instance() if not provided)
        
        Returns:
            bool: True if successful, False otherwise
        """
        # Only set once
        if IconManager._taskbar_icon_set:
            self._log("Taskbar icon already set, skipping", 'debug')
            return True
        
        # Only for Windows
        if sys.platform != 'win32':
            self._log("Not Windows, skipping taskbar icon", 'debug')
            return True
        
        # Ensure window is ready
        if not window or not window.isVisible():
            self._log("Window not ready for taskbar icon", 'warning')
            return False
        
        try:
            if not app:
                app = QApplication.instance()
            
            if not app:
                self._log("No QApplication instance", 'error')
                return False
            
            if not self.icon_path:
                self._log("No icon path available", 'warning')
                return False
            
            # Import Windows-specific helper
            from utils.app_setup_helper import set_windows_taskbar_icon
            
            success = set_windows_taskbar_icon(app, self.icon_path, self.logger, window)
            
            if success:
                IconManager._taskbar_icon_set = True
                self._log("Taskbar icon set successfully")
            else:
                self._log("Taskbar icon setting failed", 'warning')
            
            return success
            
        except Exception as e:
            self._log(f"Failed to set taskbar icon: {e}", 'error')
            return False
    
    def is_icon_set(self) -> bool:
        """Check if application icon has been set"""
        return IconManager._icon_set
    
    def is_taskbar_icon_set(self) -> bool:
        """Check if taskbar icon has been set"""
        return IconManager._taskbar_icon_set
    
    def reset(self):
        """Reset state (for testing purposes only)"""
        IconManager._icon_set = False
        IconManager._taskbar_icon_set = False
        self._log("Icon manager state reset", 'debug')


# Singleton instance
_icon_manager = IconManager()


def get_icon_manager() -> IconManager:
    """Get the singleton IconManager instance"""
    return _icon_manager
