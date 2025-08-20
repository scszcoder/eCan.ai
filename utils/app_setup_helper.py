import os
import sys
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication
from config.app_info import app_info

# Windows-specific imports
if sys.platform == 'win32':
    try:
        import ctypes
    except ImportError:
        ctypes = None

# macOS-specific imports
if sys.platform == 'darwin':
    try:
        from setproctitle import setproctitle
    except ImportError:
        setproctitle = None
    
    try:
        import Foundation
        import AppKit
    except ImportError:
        Foundation = None
        AppKit = None

def setup_application_info(app, logger=None):
    """
    Set up basic application information
    Including name, version, organization info, etc.
    """
    if not app:
        if logger:
            logger.error("QApplication instance is required")
        return False
    
    try:
        # Basic application information
        app.setApplicationName("eCan")
        app.setApplicationDisplayName("eCan")
        app.setOrganizationName("eCan Team")
        app.setOrganizationDomain("ecan.app")
        
        # Read version information
        version = "1.0.0"
        try:
            # Get correct resource path (supports PyInstaller packaging environment)
            if hasattr(sys, '_MEIPASS'):
                # PyInstaller packaging environment
                base_path = sys._MEIPASS
            else:
                # Development environment - from utils/app_setup_helper.py to project root
                base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

            # Try multiple possible VERSION file locations
            version_paths = [
                os.path.join(base_path, "VERSION"),  # PyInstaller resource directory or project root
                "VERSION",  # Current directory
                os.path.join(os.path.dirname(__file__), "..", "VERSION"),  # Project root directory
                os.path.join(os.getcwd(), "VERSION"),  # Working directory
            ]

            for version_path in version_paths:
                if os.path.exists(version_path):
                    with open(version_path, "r", encoding="utf-8") as f:
                        version = f.read().strip()
                    break
        except Exception as e:
            if logger:
                logger.warning(f"Failed to read VERSION file: {e}")
            pass
        
        app.setApplicationVersion(version)
        
        if logger:
            logger.info(f"Application info setup completed: eCan v{version}")

        # Platform-specific settings
        if sys.platform == 'darwin':
            _setup_macos_app_info(app, logger)
        elif sys.platform == 'win32':
            _setup_windows_app_info(app, logger)
        
        return True
        
    except Exception as e:
        if logger:
            logger.error(f"Failed to set up application info: {e}")
        return False

def _setup_macos_app_info(app, logger=None):
    """Set up macOS-specific application information"""
    try:
        # Set process name
        if setproctitle:
            setproctitle("eCan")
            if logger:
                logger.info("macOS process name set to: eCan")
        
        # Set macOS native application information
        if Foundation and AppKit:
            try:
                # Get current application
                ns_app = AppKit.NSApplication.sharedApplication()

                # Set application activation policy to ensure proper Dock display
                ns_app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyRegular)

                # Create virtual bundle information
                bundle_info = {
                    'CFBundleName': 'eCan',
                    'CFBundleDisplayName': 'eCan',
                    'CFBundleIdentifier': 'com.ecan.app',
                    'CFBundleVersion': app.applicationVersion(),
                    'CFBundleShortVersionString': app.applicationVersion()
                }
                
                # Try to set bundle information
                bundle = Foundation.NSBundle.mainBundle()
                if bundle:
                    info_dict = bundle.infoDictionary()
                    if info_dict:
                        for key, value in bundle_info.items():
                            info_dict[key] = value

                # Ensure application name is set correctly
                # This helps avoid menu duplication issues
                if hasattr(ns_app, 'setApplicationIconImage_'):
                    # If there's an icon, set application icon
                    pass
                
                if logger:
                    logger.info("macOS native application info setup completed")

            except Exception as e:
                if logger:
                    logger.warning(f"macOS native application info setup failed: {e}")

    except Exception as e:
        if logger:
            logger.warning(f"macOS application info setup failed: {e}")

def _setup_windows_app_info(app, logger=None):
    """Set up Windows-specific application information"""
    try:
        if sys.platform == 'win32' and ctypes:
            # Set application user model ID
            app_id = "eCan.AI.App"
            shell32 = ctypes.windll.shell32
            shell32.SetCurrentProcessExplicitAppUserModelID(app_id)

            if logger:
                logger.info(f"Windows application ID set to: {app_id}")

    except Exception as e:
        if logger:
            logger.warning(f"Windows application info setup failed: {e}")

def set_windows_taskbar_icon(app, icon_path, logger=None):
    """
    Windows-specific taskbar icon setting
    """
    if sys.platform != 'win32' or not ctypes or not icon_path:
        return False

    try:
        print(f"[DEBUG] Setting Windows taskbar icon: {icon_path}")

        # Method 1: Set application user model ID (AppUserModelID)
        app_id = "eCan.AI.App"
        shell32 = ctypes.windll.shell32
        shell32.SetCurrentProcessExplicitAppUserModelID(app_id)

        # Method 2: Clear icon cache and force refresh
        try:
            # Get main window handle
            main_window = app.activeWindow()
            if main_window:
                hwnd = int(main_window.winId())
                user32 = ctypes.windll.user32

                # If it's an .ico file, try to set it directly
                if icon_path.endswith('.ico') and os.path.exists(icon_path):
                    # Load icon
                    hicon_large = user32.LoadImageW(
                        None, icon_path, 1,  # IMAGE_ICON
                        32, 32,  # 32x32 for large icon
                        0x00000010  # LR_LOADFROMFILE
                    )
                    hicon_small = user32.LoadImageW(
                        None, icon_path, 1,  # IMAGE_ICON
                        16, 16,  # 16x16 for small icon
                        0x00000010  # LR_LOADFROMFILE
                    )

                    if hicon_large:
                        # Set large icon (taskbar)
                        user32.SendMessageW(hwnd, 0x0080, 1, hicon_large)  # WM_SETICON, ICON_LARGE
                        print(f"[DEBUG] Set large icon (32x32) for taskbar")

                    if hicon_small:
                        # Set small icon (title bar)
                        user32.SendMessageW(hwnd, 0x0080, 0, hicon_small)  # WM_SETICON, ICON_SMALL
                        print(f"[DEBUG] Set small icon (16x16) for title bar")

                    # Force refresh taskbar
                    user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0020 | 0x0004 | 0x0001)  # SWP_FRAMECHANGED | SWP_NOZORDER | SWP_NOSIZE

        except Exception as e:
            print(f"[DEBUG] Failed to set window icon via API: {e}")
            if logger:
                logger.warning(f"Failed to set window icon via API: {e}")

        if logger:
            logger.info(f"Set AppUserModelID: {app_id} and attempted icon setting")
        return True

    except Exception as e:
        print(f"[DEBUG] Windows taskbar icon setup failed: {e}")
        if logger:
            logger.warning(f"Failed to set Windows taskbar icon: {e}")
        return False

def clear_windows_icon_cache(logger=None):
    """
    Clear Windows icon cache (use with caution, will restart Explorer)
    """
    if sys.platform != 'win32':
        return False

    try:
        import subprocess

        print("[DEBUG] Note: Icon cache clearing requires Explorer restart")
        print("[DEBUG] This is optional and may cause temporary desktop disruption")

        if logger:
            logger.info("Windows icon cache clearing is available but not automatically executed")

        return True

    except Exception as e:
        print(f"[DEBUG] Icon cache clearing not available: {e}")
        if logger:
            logger.warning(f"Icon cache clearing not available: {e}")
        return False

def set_app_icon(app, logger=None):
    """
    Automatically find and set application icon based on current platform.
    """
    resource_path = app_info.app_resources_path

    # Debug info: print actual resource path used
    print(f"[DEBUG] Resource path: {resource_path}")
    if logger:
        logger.info(f"Using resource path: {resource_path}")

    # Select icon candidates based on platform
    if sys.platform == 'darwin':
        icon_candidates = [
            os.path.join(resource_path, "images", "logos", "rounded", "dock_512x512.png"),
            os.path.join(resource_path, "images", "logos", "rounded", "dock_256x256.png"),
            os.path.join(resource_path, "images", "logos", "rounded", "dock_128x128.png"),
            os.path.join(resource_path, "images", "logos", "desktop_256x256.png"),
            os.path.join(resource_path, "images", "logos", "desktop_128x128.png"),
        ]
    elif sys.platform == 'win32':
        icon_candidates = [
            os.path.join(resource_path, "images", "logos", "icon_multi.ico"),
            os.path.join(resource_path, "images", "logos", "desktop_256x256.png"),
            os.path.join(resource_path, "images", "logos", "taskbar_32x32.png"),
            os.path.join(resource_path, "images", "logos", "taskbar_16x16.png"),
        ]
    else:
        icon_candidates = [
            os.path.join(resource_path, "images", "logos", "desktop_256x256.png"),
            os.path.join(resource_path, "images", "logos", "desktop_128x128.png"),
        ]

    # Find first existing icon file
    icon_path = None
    print(f"[DEBUG] Checking {len(icon_candidates)} icon candidates:")
    for i, candidate in enumerate(icon_candidates):
        exists = os.path.exists(candidate)
        print(f"[DEBUG] {i+1}. {candidate} - {'EXISTS' if exists else 'NOT FOUND'}")
        if logger:
            logger.info(f"Icon candidate {i+1}: {candidate} - {'found' if exists else 'not found'}")
        if exists and icon_path is None:
            icon_path = candidate

    if icon_path:
        print(f"[DEBUG] Selected icon: {icon_path}")
        # Set application icon
        app_icon = QIcon(icon_path)
        app.setWindowIcon(app_icon)

        # Windows-specific settings
        if sys.platform == 'win32':
            success = set_windows_taskbar_icon(app, icon_path, logger)
            if not success:
                print("[DEBUG] Windows taskbar icon setting failed")
                print("[DEBUG] If taskbar shows wrong icon, try:")
                print("[DEBUG] 1. Restart the application")
                print("[DEBUG] 2. Clear Windows icon cache manually")
                print("[DEBUG] 3. Check if .ico file is valid")

        if logger:
            logger.info(f"Successfully loaded application icon from: {icon_path}")

        # Provide icon cache clearing instructions
        if sys.platform == 'win32':
            print("[DEBUG] If taskbar icon doesn't update:")
            print("[DEBUG] - Windows may be using cached icon")
            print("[DEBUG] - Try restarting the application")
            print("[DEBUG] - Or manually clear icon cache")

    else:
        print(f"[DEBUG] No icon found! Checked paths:")
        for candidate in icon_candidates:
            print(f"[DEBUG]   - {candidate}")
        if logger:
            logger.warning(f"No application icon found in: {icon_candidates}")

def set_app_icon_delayed(app, logger=None):
    """
    Set application icon with delay to ensure main window is created
    """
    from PySide6.QtCore import QTimer

    def delayed_setup():
        set_app_icon(app, logger)

    QTimer.singleShot(100, delayed_setup)