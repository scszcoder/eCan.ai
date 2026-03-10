"""
Icon Manager - Centralized icon management for the application
Solves the window flashing issue by ensuring icons are set only once at the right time.
"""

import os
import sys
from typing import Optional
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtCore import Qt


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
        """Internal logging helper - falls back to print if logger not available"""
        prefix = "[IconManager] "
        full_message = f"{prefix}{message}"
        
        if self.logger:
            if level == 'debug':
                self.logger.debug(full_message)
            elif level == 'warning':
                self.logger.warning(full_message)
            elif level == 'error':
                self.logger.error(full_message)
            else:
                self.logger.info(full_message)
        else:
            # Fallback to print during early startup when logger is not yet available
            print(full_message)
    
    def _resource_base_paths(self):
        """Multiple base paths so icon is found in dev (cwd / run from anywhere)."""
        bases = []
        # Prefer __file__-relative path first so icon is found regardless of cwd (e.g. run from IDE)
        try:
            file_based = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "resource"))
            file_based = os.path.abspath(file_based)
            bases.append(file_based)
        except Exception:
            pass
        try:
            from config.app_info import app_info
            p = os.path.abspath(app_info.app_resources_path)
            if p not in bases:
                bases.append(p)
        except Exception:
            pass
        cwd_resource = os.path.abspath(os.path.join(os.getcwd(), "resource"))
        if cwd_resource not in bases:
            bases.append(cwd_resource)
        return bases

    def _find_icon_path(self) -> Optional[str]:
        """
        Find the application icon file. Tries app_info, cwd, and __file__-relative paths.
        Linux: prefer PNG for taskbar/dock.
        """
        try:
            bases = self._resource_base_paths()
            if sys.platform == 'darwin':
                rels = [
                    "images/logos/rounded/dock_512x512.png",
                    "images/logos/dock_512x512.png",
                    "images/logos/desktop_256x256.png",
                ]
            elif sys.platform.startswith("linux"):
                rels = [
                    "images/logos/desktop_256x256.png",
                    "images/logos/desktop_128x128.png",
                    "images/logos/desktop_64x64.png",
                    "images/logos/dock_256x256.png",
                    "images/logos/taskbar_32x32.png",
                    "images/logos/taskbar_16x16.png",
                    "images/logos/icon_multi.ico",
                ]
            else:
                rels = [
                    "images/logos/icon_multi.ico",
                    "images/logos/desktop_256x256.png",
                ]
            # macOS: only rels (original behavior, no root eCan.ico).
            # Linux: prefer PNG for taskbar; search rels first, then root ICO.
            # Windows: root ICO first, then rels.
            is_linux = sys.platform.startswith("linux")
            is_darwin = sys.platform == "darwin"
            if is_linux:
                for base in bases:
                    for rel in rels:
                        candidate = os.path.join(base, rel)
                        if os.path.isfile(candidate):
                            self.icon_path = os.path.abspath(candidate)
                            self._log(f"Resolved icon: {self.icon_path}", 'info')
                            return self.icon_path
            if not is_darwin:
                for base in bases:
                    root_ico = os.path.join(os.path.dirname(base), "eCan.ico")
                    if os.path.isfile(root_ico):
                        self.icon_path = os.path.abspath(root_ico)
                        self._log(f"Resolved icon: {self.icon_path}", 'info')
                        return self.icon_path
            for base in bases:
                for rel in rels:
                    candidate = os.path.join(base, rel)
                    if os.path.isfile(candidate):
                        self.icon_path = os.path.abspath(candidate)
                        self._log(f"Resolved icon: {self.icon_path}", 'info')
                        return self.icon_path
            if os.environ.get("ECAN_ICON_DEBUG"):
                self._log(f"No icon found. Bases: {bases}", 'warning')
            return None
        except Exception as e:
            if self.logger:
                self.logger.error(f"[IconManager] Failed to find icon: {e}")
            return None
    
    def set_application_icon(self, app: QApplication) -> bool:
        """
        Set Qt application icon (QApplication.setWindowIcon).
        
        This sets the default icon for all application windows.
        - macOS: Used for window title bar and Dock (if .app doesn't have .icns)
        - Windows: Used for window title bar only (taskbar requires separate setup)
        - Linux: Used for window manager and taskbar
        
        Call timing: Early in startup (right after QApplication creation)
        
        Returns:
            bool: True if successful, False otherwise
        """
        if IconManager._icon_set:
            self._log("Application icon already set, skipping", 'debug')
            return True
        
        if not self.icon_path:
            self._find_icon_path()
        if not self.icon_path:
            self._log("No icon path available", 'warning')
            return False
        
        try:
            if sys.platform.startswith("linux"):
                app_icon = self._make_icon_with_sizes(self.icon_path)
                if app_icon.isNull():
                    app_icon = QIcon(self.icon_path)
            else:
                app_icon = QIcon(self.icon_path)
            app.setWindowIcon(app_icon)
            IconManager._icon_set = True
            self._log(f"Application icon set: {self.icon_path}")
            
            return True
        except Exception as e:
            self._log(f"Failed to set application icon: {e}", 'error')
            return False

    def _make_icon_with_sizes(self, path: str) -> QIcon:
        """Build QIcon with explicit sizes for Linux taskbar/dock."""
        icon = QIcon()
        for size in (16, 22, 24, 32, 48, 64, 128, 256):
            pix = QPixmap(path)
            if pix.isNull():
                continue
            scaled = pix.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            if not scaled.isNull():
                icon.addPixmap(scaled, QIcon.Normal, QIcon.Off)
        if icon.isNull():
            icon = QIcon(path)
        return icon

    def get_icon_for_window(self) -> QIcon:
        """Return QIcon for setWindowIcon (multi-size on Linux). Re-resolves path if needed."""
        if not self.icon_path:
            self._find_icon_path()
        if not self.icon_path:
            return QIcon()
        if sys.platform.startswith("linux"):
            return self._make_icon_with_sizes(self.icon_path)
        return QIcon(self.icon_path)
    
    def set_window_taskbar_icon(self, window, app: Optional[QApplication] = None) -> bool:
        """
        Set Windows taskbar icon for a specific window (Windows-only operation).
        
        Why Windows needs special handling:
        - Windows taskbar uses different icon than window title bar
        - Requires valid window handle (HWND) from visible window
        - In frozen/packaged builds, extracts icon from EXE resources
        - Must be called AFTER window is visible and stable
        
        Call timing: Delayed by 1 second after window.show() (see WebGUI._setup_taskbar_icon_via_manager)
        
        Args:
            window: The QMainWindow instance (must be visible)
            app: Optional QApplication instance (auto-detected if not provided)
        
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
            
            # Import Windows-specific helper (handles frozen/packaged builds)
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
