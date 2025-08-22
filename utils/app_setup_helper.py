import os
import sys
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication
import setproctitle
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
                # PyInstaller packaging environment - VERSION file is in the root of _MEIPASS
                base_path = sys._MEIPASS
                if logger:
                    logger.debug(f"PyInstaller environment detected, base_path: {base_path}")
            else:
                # Development environment - from utils/app_setup_helper.py to project root
                base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                if logger:
                    logger.debug(f"Development environment detected, base_path: {base_path}")

            # Try multiple possible VERSION file locations
            if hasattr(sys, '_MEIPASS'):
                # PyInstaller environment - VERSION is in _internal directory
                version_paths = [
                    os.path.join(base_path, "VERSION"),  # PyInstaller _MEIPASS root
                    os.path.join(base_path, "_internal", "VERSION"),  # PyInstaller _internal directory
                    os.path.join(os.path.dirname(sys.executable), "VERSION"),  # Executable directory
                    os.path.join(os.path.dirname(sys.executable), "_internal", "VERSION"),  # Executable _internal
                ]
            else:
                # Development environment
                version_paths = [
                    os.path.join(base_path, "VERSION"),  # Project root
                    os.path.join(os.path.dirname(__file__), "..", "VERSION"),  # Project root directory
                    os.path.join(os.getcwd(), "VERSION"),  # Working directory
                    "VERSION",  # Current directory
                ]

            version_found = False
            for version_path in version_paths:
                if logger:
                    logger.debug(f"Trying VERSION file path: {version_path}")
                if os.path.exists(version_path) and os.path.isfile(version_path):
                    try:
                        with open(version_path, "r", encoding="utf-8") as f:
                            version_content = f.read().strip()
                            if version_content:  # Make sure it's not empty
                                version = version_content
                                version_found = True
                                if logger:
                                    logger.info(f"VERSION file found at: {version_path}, version: {version}")
                                break
                    except Exception as read_error:
                        if logger:
                            logger.warning(f"Failed to read VERSION file at {version_path}: {read_error}")
                        continue
                else:
                    if logger:
                        logger.debug(f"VERSION file not found at: {version_path}")

            if not version_found and logger:
                logger.warning(f"VERSION file not found in any of the attempted paths: {version_paths}")

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
        # Import Foundation and AppKit if available
        if sys.platform  == 'darwin':
            import Foundation
            import AppKit
        else:
            Foundation = None
            AppKit = None

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
            # Set application user model ID (must be done very early)
            app_id = "eCan.AI.App"
            shell32 = ctypes.windll.shell32
            result = shell32.SetCurrentProcessExplicitAppUserModelID(app_id)

            # Set process title early for better Windows integration
            try:
                import setproctitle
                setproctitle.setproctitle("eCan")
                if logger:
                    logger.debug("Process title set to: eCan")
            except ImportError:
                if logger:
                    logger.debug("setproctitle not available, skipping process title setting")

            # Set additional Windows-specific properties
            try:
                # Set window class name for better Windows integration
                app.setApplicationName("eCan")
                app.setApplicationDisplayName("eCan")
                app.setApplicationVersion("1.0.0")
                app.setOrganizationName("eCan")
                app.setOrganizationDomain("ecan.ai")

                if logger:
                    logger.debug("Windows application properties set")
            except Exception as e:
                if logger:
                    logger.warning(f"Failed to set Windows application properties: {e}")

            # Try to set the console window title as well
            try:
                kernel32 = ctypes.windll.kernel32
                kernel32.SetConsoleTitleW("eCan")
                if logger:
                    logger.debug("Console title set to: eCan")
            except Exception as e:
                if logger:
                    logger.debug(f"Failed to set console title: {e}")

            if logger:
                logger.info(f"Windows application ID set to: {app_id} (result: {result})")

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
        if logger:
            logger.debug(f"Setting Windows taskbar icon: {icon_path}")

        # Method 1: Set application user model ID (AppUserModelID)
        app_id = "eCan.AI.App"
        shell32 = ctypes.windll.shell32
        shell32.SetCurrentProcessExplicitAppUserModelID(app_id)

        # Method 2: Set window icon using Windows API
        try:
            # Get main window handle
            main_window = app.activeWindow()
            if main_window:
                hwnd = int(main_window.winId())
                user32 = ctypes.windll.user32

                # Try to set icon based on file type
                if os.path.exists(icon_path):
                    if icon_path.endswith('.ico'):
                        # Load ICO file directly
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
                    else:
                        # For PNG files, try to find corresponding ICO file or use Qt conversion
                        ico_path = None

                        # First, try to find icon_multi.ico in the same directory
                        icon_dir = os.path.dirname(icon_path)
                        ico_candidates = [
                            os.path.join(icon_dir, "icon_multi.ico"),
                            os.path.join(icon_dir, "taskbar_32x32.ico"),
                            os.path.join(icon_dir, "taskbar_16x16.ico")
                        ]

                        for ico_candidate in ico_candidates:
                            if os.path.exists(ico_candidate):
                                ico_path = ico_candidate
                                break

                        if ico_path:
                            # Use found ICO file
                            hicon_large = user32.LoadImageW(
                                None, ico_path, 1,  # IMAGE_ICON
                                32, 32,  # 32x32 for large icon
                                0x00000010  # LR_LOADFROMFILE
                            )
                            hicon_small = user32.LoadImageW(
                                None, ico_path, 1,  # IMAGE_ICON
                                16, 16,  # 16x16 for small icon
                                0x00000010  # LR_LOADFROMFILE
                            )
                            if logger:
                                logger.debug(f"Using ICO file for Windows API: {ico_path}")
                        else:
                            # Fallback: let Qt handle the icon, skip Windows API
                            if logger:
                                logger.debug(f"No ICO file found, using Qt icon handling for: {icon_path}")
                            hicon_large = None
                            hicon_small = None

                    if hicon_large:
                        # Set large icon (taskbar)
                        user32.SendMessageW(hwnd, 0x0080, 1, hicon_large)  # WM_SETICON, ICON_LARGE
                        if logger:
                            logger.debug("Set large icon (32x32) for taskbar")

                    if hicon_small:
                        # Set small icon (title bar)
                        user32.SendMessageW(hwnd, 0x0080, 0, hicon_small)  # WM_SETICON, ICON_SMALL
                        if logger:
                            logger.debug("Set small icon (16x16) for title bar")

                    # Force refresh taskbar
                    user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0020 | 0x0004 | 0x0001)  # SWP_FRAMECHANGED | SWP_NOZORDER | SWP_NOSIZE

        except Exception as e:
            if logger:
                logger.warning(f"Failed to set window icon via API: {e}")

        if logger:
            logger.info(f"Set AppUserModelID: {app_id} and attempted icon setting")
        return True

    except Exception as e:
        if logger:
            logger.warning(f"Windows taskbar icon setup failed: {e}")
        return False

def clear_windows_icon_cache(logger=None):
    """
    Clear Windows icon cache (use with caution, will restart Explorer)
    """
    if sys.platform != 'win32':
        return False

    try:
        import subprocess

        if logger:
            logger.info("Note: Icon cache clearing requires Explorer restart")
            logger.info("This is optional and may cause temporary desktop disruption")
            logger.info("Windows icon cache clearing is available but not automatically executed")

        return True

    except Exception as e:
        if logger:
            logger.warning(f"Icon cache clearing not available: {e}")
        return False

def set_app_icon(app, logger=None):
    """
    Automatically find and set application icon based on current platform.
    """
    resource_path = app_info.app_resources_path

    # Debug info: log actual resource path used
    if logger:
        logger.debug(f"Resource path: {resource_path}")
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
            # Prefer high-quality root directory ICO file first
            os.path.join(os.path.dirname(resource_path), "eCan.ico"),
            # Then try resource directory ICO files
            os.path.join(resource_path, "images", "logos", "icon_multi.ico"),
            # Fallback to PNG files
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
    if logger:
        logger.debug(f"Checking {len(icon_candidates)} icon candidates:")
    for i, candidate in enumerate(icon_candidates):
        exists = os.path.exists(candidate)
        if logger:
            logger.debug(f"{i+1}. {candidate} - {'EXISTS' if exists else 'NOT FOUND'}")
            logger.info(f"Icon candidate {i+1}: {candidate} - {'found' if exists else 'not found'}")
        if exists and icon_path is None:
            icon_path = candidate

    if icon_path:
        if logger:
            logger.debug(f"Selected icon: {icon_path}")
        # Set application icon
        app_icon = QIcon(icon_path)
        app.setWindowIcon(app_icon)

        # Windows-specific settings
        if sys.platform == 'win32':
            success = set_windows_taskbar_icon(app, icon_path, logger)
            if not success:
                if logger:
                    logger.warning("Windows taskbar icon setting failed")
                    logger.info("If taskbar shows wrong icon, try:")
                    logger.info("1. Restart the application")
                    logger.info("2. Clear Windows icon cache manually")
                    logger.info("3. Check if .ico file is valid")

        if logger:
            logger.info(f"Successfully loaded application icon from: {icon_path}")

        # Provide icon cache clearing instructions
        if sys.platform == 'win32':
            if logger:
                logger.info("If taskbar icon doesn't update:")
                logger.info("- Windows may be using cached icon")
                logger.info("- Try restarting the application")
                logger.info("- Or manually clear icon cache")

    else:
        if logger:
            logger.warning("No icon found! Checked paths:")
            for candidate in icon_candidates:
                logger.debug(f"  - {candidate}")
            logger.warning(f"No application icon found in: {icon_candidates}")

def set_app_icon_early(app, logger=None):
    """
    Set application icon as early as possible, before splash screen
    This ensures the taskbar shows the correct icon from the start
    """
    def log_msg(msg, level='info'):
        """Helper to log message or print if logger not available"""
        if logger:
            if level == 'debug':
                logger.debug(msg)
            elif level == 'warning':
                logger.warning(msg)
            elif level == 'error':
                logger.error(msg)
            else:
                logger.info(msg)
        else:
            print(f"[EARLY_ICON] {msg}")

    try:
        resource_path = app_info.app_resources_path
        log_msg(f"Early icon setting started, resource_path: {resource_path}")

        # Windows-specific early icon setting
        if sys.platform == 'win32':
            # Set AppUserModelID first (must be done early)
            try:
                import ctypes
                shell32 = ctypes.windll.shell32
                app_id = "eCan.AI.App"
                result = shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
                log_msg(f"Early AppUserModelID set: {app_id} (result: {result})", 'debug')

                # Set process title early for better Windows integration
                try:
                    import setproctitle
                    setproctitle.setproctitle("eCan")
                    log_msg("Early process title set to: eCan", 'debug')
                except ImportError:
                    log_msg("setproctitle not available for early process title setting", 'debug')

                # Set console title early
                try:
                    kernel32 = ctypes.windll.kernel32
                    kernel32.SetConsoleTitleW("eCan")
                    log_msg("Early console title set to: eCan", 'debug')
                except Exception as e:
                    log_msg(f"Failed to set early console title: {e}", 'debug')

            except Exception as e:
                log_msg(f"Failed to set early AppUserModelID: {e}", 'warning')

            # Find and set icon immediately
            icon_candidates = [
                os.path.join(os.path.dirname(resource_path), "eCan.ico"),
                os.path.join(resource_path, "images", "logos", "icon_multi.ico"),
                os.path.join(resource_path, "images", "logos", "desktop_256x256.png"),
            ]

            icon_path = None
            for i, candidate in enumerate(icon_candidates):
                if os.path.exists(candidate):
                    icon_path = candidate
                    log_msg(f"Found icon candidate {i+1}: {candidate}")
                    break
                else:
                    log_msg(f"Icon candidate {i+1} not found: {candidate}", 'debug')

            if icon_path:
                # Set Qt application icon immediately
                from PySide6.QtGui import QIcon
                app_icon = QIcon(icon_path)
                app.setWindowIcon(app_icon)
                log_msg(f"Set Qt application icon: {icon_path}")

                # Set Windows taskbar icon immediately
                success = set_windows_taskbar_icon(app, icon_path, logger)
                log_msg(f"Windows taskbar icon setting: {'success' if success else 'failed'}")

                log_msg(f"Early icon set successfully: {icon_path}")
                return True
            else:
                log_msg("No icon found for early setting", 'warning')
                return False
        else:
            # For other platforms, use standard icon setting
            log_msg("Non-Windows platform, using standard icon setting")
            return set_app_icon(app, logger)

    except Exception as e:
        log_msg(f"Early icon setting failed: {e}", 'error')
        return False

def set_app_icon_delayed(app, logger=None):
    """
    Set application icon with delay to ensure main window is created
    """
    from PySide6.QtCore import QTimer

    def delayed_setup():
        set_app_icon(app, logger)

    QTimer.singleShot(100, delayed_setup)