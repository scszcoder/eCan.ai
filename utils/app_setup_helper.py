import os
import sys
import time
from PySide6.QtGui import QIcon
import setproctitle

try:
    from config.app_info import app_info
except ImportError:
    app_info = None


def get_app_user_model_id():
    """
    Unified function to get AppUserModelID

    Returns:
        str: AppUserModelID, returns default value if reading fails
    """
    try:
        import json
        from pathlib import Path
        config_path = Path(__file__).parent.parent / "build_system" / "build_config.json"
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        return config.get("app", {}).get("app_user_model_id", "eCan.AI.Assistant")
    except Exception:
        return "eCan.AI.Assistant"  # Fallback stable ID


def set_windows_app_user_model_id(logger=None):
    """
    Unified function to set Windows AppUserModelID

    Args:
        logger: Optional logger

    Returns:
        tuple: (app_id, result) - AppUserModelID and setting result
    """
    if sys.platform != 'win32':
        return None, False

    try:
        import ctypes
        app_id = get_app_user_model_id()
        shell32 = ctypes.windll.shell32
        result = shell32.SetCurrentProcessExplicitAppUserModelID(app_id)

        if logger:
            logger.debug(f"Set AppUserModelID: {app_id} (result: {result})")

        return app_id, result
    except Exception as e:
        if logger:
            logger.warning(f"Failed to set AppUserModelID: {e}")
        return None, False


def read_version_file(version_paths, logger=None):
    """
    Unified version file reading function, supports development and packaged environments

    Args:
        version_paths: List of version file paths to try
        logger: Optional logger

    Returns:
        str: Version number read, returns "1.0.0" if failed
    """
    for version_path in version_paths:
        if logger:
            logger.debug(f"Trying VERSION file path: {version_path}")

        # Check if it's a file
        if os.path.exists(version_path) and os.path.isfile(version_path):
            try:
                with open(version_path, "r", encoding="utf-8") as f:
                    version_content = f.read().strip()
                    if version_content:  # Ensure not empty
                        if logger:
                            logger.info(f"VERSION file found at: {version_path}, version: {version_content}")
                        return version_content
            except Exception as read_error:
                if logger:
                    logger.warning(f"Failed to read VERSION file at {version_path}: {read_error}")
                continue
        # Check if it's a directory containing VERSION file (PyInstaller packaged case)
        elif os.path.exists(version_path) and os.path.isdir(version_path):
            nested_version_path = os.path.join(version_path, "VERSION")
            if logger:
                logger.debug(f"Found VERSION directory, trying nested path: {nested_version_path}")
            if os.path.exists(nested_version_path) and os.path.isfile(nested_version_path):
                try:
                    with open(nested_version_path, "r", encoding="utf-8") as f:
                        version_content = f.read().strip()
                        if version_content:  # Ensure not empty
                            if logger:
                                logger.info(f"VERSION file found in directory at: {nested_version_path}, version: {version_content}")
                            return version_content
                except Exception as read_error:
                    if logger:
                        logger.warning(f"Failed to read nested VERSION file at {nested_version_path}: {read_error}")
                    continue
            else:
                if logger:
                    logger.debug(f"No VERSION file found in directory: {version_path}")
        else:
            if logger:
                logger.debug(f"VERSION file not found at: {version_path}")

    # If all paths fail, return default version
    if logger:
        logger.warning(f"VERSION file not found in any of the attempted paths: {version_paths}")
    return "1.0.0"

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
        app.setApplicationName("eCan.ai")
        app.setApplicationDisplayName("eCan.ai")
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

            # Use unified version reading function
            version = read_version_file(version_paths, logger)

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
            # Note: AppUserModelID should be stable across versions for proper Windows integration
            app_id, result = set_windows_app_user_model_id(logger)

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
                app.setApplicationName("eCan.ai")
                app.setApplicationDisplayName("eCan.ai")
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
                kernel32.SetConsoleTitleW("eCan.ai")
                if logger:
                    logger.debug("Console title set to: eCan.ai")
            except Exception as e:
                if logger:
                    logger.debug(f"Failed to set console title: {e}")

            if logger:
                logger.info(f"Windows application ID set to: {app_id} (result: {result})")

    except Exception as e:
        if logger:
            logger.warning(f"Windows application info setup failed: {e}")

def set_windows_taskbar_icon(app, icon_path, logger=None, target_window=None):
    """
    Windows-specific taskbar icon setting
    """
    if sys.platform != 'win32' or not icon_path or not os.path.exists(icon_path):
        return False

    try:
        import ctypes
    except ImportError:
        if logger:
            logger.warning("ctypes not available for Windows icon setting")
        return False

    try:
        # Set application user model ID
        app_id, _ = set_windows_app_user_model_id(logger)

        # Only handle ICO files
        if not icon_path.endswith('.ico'):
            return False

        user32 = ctypes.windll.user32

        # Get window handle
        hwnd = None

        # Prefer using specified target window
        if target_window:
            try:
                hwnd = int(target_window.winId())
            except:
                pass

        # Fallback: get active window from Qt application
        if not hwnd:
            try:
                main_window = app.activeWindow()
                if main_window:
                    hwnd = int(main_window.winId())
            except:
                pass

        # Last resort: iterate through top-level windows
        if not hwnd:
            try:
                for widget in app.topLevelWidgets():
                    if widget.isVisible() and hasattr(widget, 'winId'):
                        hwnd = int(widget.winId())
                        break
            except:
                pass

        if not hwnd:
            if logger:
                logger.warning("Could not get window handle")
            return False

        # Load and set icon (standard implementation: prefer EXE resource, then file, finally fallback)
        try:
            user32 = ctypes.windll.user32
            success = False

            # 1) Prefer extracting icon from executable resource (EXE embedded, multi-size, most stable)
            try:
                exe_path = sys.executable if getattr(sys, 'frozen', False) else None
                if exe_path and os.path.exists(exe_path):
                    from ctypes import wintypes
                    shell32 = ctypes.windll.shell32
                    hicon_large = wintypes.HANDLE()
                    hicon_small = wintypes.HANDLE()
                    count = shell32.ExtractIconExW(exe_path, 0, ctypes.byref(hicon_large), ctypes.byref(hicon_small), 1)
                    if count > 0:
                        if hicon_large.value:
                            user32.SendMessageW(hwnd, 0x0080, 1, hicon_large.value)
                            success = True
                            if logger:
                                logger.debug("Set large icon (resource) for taskbar")
                        if hicon_small.value:
                            user32.SendMessageW(hwnd, 0x0080, 0, hicon_small.value)
                            success = True
                            if logger:
                                logger.debug("Set small icon (resource) for title bar")
            except Exception as e:
                if logger:
                    logger.debug(f"Resource icon extract failed: {e}")

            # 2) If resource method unsuccessful, fall back to file path loading (eCan.ico)
            if not success:
                LR_LOADFROMFILE = 0x00000010
                LR_DEFAULTSIZE = 0x00000040
                IMAGE_ICON = 1

                hicon_large = user32.LoadImageW(None, icon_path, IMAGE_ICON, 32, 32, LR_LOADFROMFILE)
                hicon_small = user32.LoadImageW(None, icon_path, IMAGE_ICON, 16, 16, LR_LOADFROMFILE)
                if not hicon_large and not hicon_small:
                    if logger:
                        logger.debug("Initial icon load failed, retrying with default size")
                    hicon_large = user32.LoadImageW(None, icon_path, IMAGE_ICON, 0, 0, LR_LOADFROMFILE | LR_DEFAULTSIZE)
                    hicon_small = user32.LoadImageW(None, icon_path, IMAGE_ICON, 0, 0, LR_LOADFROMFILE | LR_DEFAULTSIZE)

                if hicon_large:
                    user32.SendMessageW(hwnd, 0x0080, 1, hicon_large)  # WM_SETICON, ICON_LARGE
                    success = True
                    if logger:
                        logger.debug("Set large icon for taskbar")
                if hicon_small:
                    user32.SendMessageW(hwnd, 0x0080, 0, hicon_small)  # WM_SETICON, ICON_SMALL
                    success = True
                    if logger:
                        logger.debug("Set small icon for title bar")

                # 3) File method still failed => use multi-size ICO in resource directory as fallback
                if not success:
                    try:
                        from config.app_info import app_info as _ai
                        res_path = _ai.app_resources_path
                        fallback_ico = os.path.join(res_path, "images", "logos", "icon_multi.ico")
                        if os.path.exists(fallback_ico):
                            if logger:
                                logger.debug(f"Retrying with fallback ICO: {fallback_ico}")
                            hicon_large = user32.LoadImageW(None, fallback_ico, IMAGE_ICON, 32, 32, LR_LOADFROMFILE)
                            hicon_small = user32.LoadImageW(None, fallback_ico, IMAGE_ICON, 16, 16, LR_LOADFROMFILE)
                            if not hicon_large and not hicon_small:
                                hicon_large = user32.LoadImageW(None, fallback_ico, IMAGE_ICON, 0, 0, LR_LOADFROMFILE | LR_DEFAULTSIZE)
                                hicon_small = user32.LoadImageW(None, fallback_ico, IMAGE_ICON, 0, 0, LR_LOADFROMFILE | LR_DEFAULTSIZE)
                            if hicon_large:
                                user32.SendMessageW(hwnd, 0x0080, 1, hicon_large)
                                success = True
                            if hicon_small:
                                user32.SendMessageW(hwnd, 0x0080, 0, hicon_small)
                                success = True
                            if success and logger:
                                logger.info("Windows taskbar icon set via fallback ICO")
                    except Exception:
                        pass

            if success:
                # Refresh window and taskbar
                # SWP_FRAMECHANGED | SWP_NOZORDER | SWP_NOSIZE | SWP_NOMOVE
                user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0020 | 0x0004 | 0x0001 | 0x0002)
                try:
                    user32.UpdateWindow(hwnd)
                    shell32 = ctypes.windll.shell32
                    shell32.SHChangeNotify(0x08000000, 0x0000, None, None)  # SHCNE_ASSOCCHANGED
                    if logger:
                        logger.debug("Forced taskbar and shell icon refresh")
                except Exception as e:
                    if logger:
                        logger.debug(f"Additional icon refresh failed: {e}")

            return success

        except Exception as e:
            if logger:
                logger.warning(f"Failed to load/set icon: {e}")
            return False

    except Exception as e:
        if logger:
            logger.warning(f"Windows taskbar icon setup failed: {e}")
        return False

def check_ico_quality(logger=None):
    """
    Simple ICO file quality check
    """
    if sys.platform != 'win32':
        return True

    try:
        # Find main ICO file
        ico_path = os.path.join(os.path.dirname(app_info.app_resources_path), "eCan.ico")

        if not os.path.exists(ico_path):
            if logger:
                logger.warning("eCan.ico not found")
            return False

        # Simple size check (handle PyInstaller one-file package early startup extraction delay)
        file_size = os.path.getsize(ico_path)
        if file_size == 0 and "_internal" in ico_path:
            # In one-file package, file may not be fully written during early startup; retry a few times
            for _ in range(10):
                time.sleep(0.1)
                try:
                    file_size = os.path.getsize(ico_path)
                    if file_size > 0:
                        break
                except Exception:
                    pass

        if file_size < 5000:  # 5KB minimum (too small ICO usually lacks 16/32 sizes or only contains PNG)
            if logger:
                logger.warning(f"ICO file too small ({file_size} bytes)")
            return False

        if logger:
            logger.debug(f"ICO file OK: {ico_path} ({file_size} bytes)")
        return True

    except Exception as e:
        if logger:
            logger.warning(f"ICO check failed: {e}")
        return False


def clear_windows_icon_cache(logger=None):
    """
    Clear Windows icon cache to fix taskbar icon issues
    """
    if sys.platform != 'win32':
        return False

    try:
        if logger:
            logger.info("Clearing Windows icon cache...")

        # Clear registry icon cache
        try:
            import winreg
            cache_keys = [
                r"Software\Classes\Local Settings\Software\Microsoft\Windows\CurrentVersion\TrayNotify"
            ]

            for key_path in cache_keys:
                try:
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
                        cache_values = ["IconStreams", "PastIconsStream"]
                        for value_name in cache_values:
                            try:
                                winreg.DeleteValue(key, value_name)
                                if logger:
                                    logger.debug(f"Cleared {value_name} from registry")
                            except FileNotFoundError:
                                pass
                except FileNotFoundError:
                    pass
        except Exception as e:
            if logger:
                logger.debug(f"Registry cache clear failed: {e}")

        # Delete file system icon cache
        cache_dir = os.path.expandvars(r'%LOCALAPPDATA%\Microsoft\Windows\Explorer')
        import glob

        deleted_count = 0
        for pattern in ['iconcache_*.db', 'thumbcache_*.db']:
            for cache_file in glob.glob(os.path.join(cache_dir, pattern)):
                try:
                    os.remove(cache_file)
                    deleted_count += 1
                except Exception:
                    pass  # File may be in use, ignore error

        # Force icon refresh using Windows API
        try:
            import ctypes
            user32 = ctypes.windll.user32
            shell32 = ctypes.windll.shell32

            # Refresh desktop and taskbar
            user32.UpdatePerUserSystemParameters(1, 0)
            shell32.SHChangeNotify(0x08000000, 0x0000, None, None)  # SHCNE_ASSOCCHANGED
            shell32.SHChangeNotify(0x00002000, 0x0000, None, None)  # SHCNE_UPDATEIMAGE

            if logger:
                logger.info("Windows icon cache cleared and refreshed")
        except Exception as e:
            if logger:
                logger.debug(f"Icon refresh failed: {e}")

        if logger and deleted_count > 0:
            logger.debug(f"Cleared {deleted_count} icon cache files")

        return True

    except Exception as e:
        if logger:
            logger.warning(f"Icon cache clearing failed: {e}")
        return False

# Global flag to avoid repeated icon fix execution
_icon_fix_executed = False

def verify_taskbar_icon_setting(target_window=None, logger=None):
    """
    Verify if taskbar icon is correctly set
    """
    if sys.platform != 'win32':
        return True

    try:
        import ctypes
        user32 = ctypes.windll.user32

        # Get window handle
        hwnd = None
        if target_window:
            try:
                hwnd = int(target_window.winId())
            except:
                pass

        if not hwnd:
            if logger:
                logger.debug("No window handle available for verification")
            return False

        # Check if window icon is set
        hicon_large = user32.SendMessageW(hwnd, 0x007F, 1, 0)  # WM_GETICON, ICON_LARGE
        hicon_small = user32.SendMessageW(hwnd, 0x007F, 0, 0)  # WM_GETICON, ICON_SMALL

        has_large = hicon_large != 0
        has_small = hicon_small != 0

        if logger:
            logger.debug(f"Icon verification: Large={has_large}, Small={has_small}")

        return has_large or has_small

    except Exception as e:
        if logger:
            logger.debug(f"Icon verification failed: {e}")
        return False

def set_app_icon(app, logger=None):
    """
    Automatically find and set application icon based on current platform.
    """
    global _icon_fix_executed

    # Windows icon fix: check ICO quality and clear cache (execute only once)
    if sys.platform == 'win32' and not _icon_fix_executed:
        check_ico_quality(logger)
        clear_windows_icon_cache(logger)
        _icon_fix_executed = True

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
    for candidate in icon_candidates:
        exists = os.path.exists(candidate)
        # if logger:
        #     logger.debug(f"{candidate} - {'EXISTS' if exists else 'NOT FOUND'}")
        #     logger.info(f"Icon candidate {i+1}: {candidate} - {'found' if exists else 'not found'}")
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
            if not success and logger:
                logger.warning("Windows taskbar icon setting failed")
                logger.info("If taskbar icon doesn't update:")
                logger.info("1. Restart the application")
                logger.info("2. Restart Windows Explorer (taskkill /f /im explorer.exe && start explorer.exe)")
                logger.info("3. Reboot computer if needed")

        if logger:
            logger.info(f"Successfully loaded application icon from: {icon_path}")

        # Provide icon cache clearing instructions
        if sys.platform == 'win32':
            if logger:
                logger.info("If taskbar icon doesn't update:")
                logger.info("- Windows may be using cached icon")
                logger.info("- Try restarting the application")
                logger.info("- Or manually clear icon cache")

        return True

    else:
        if logger:
            logger.warning("No icon found! Checked paths:")
            for candidate in icon_candidates:
                logger.debug(f"  - {candidate}")
            logger.warning(f"No application icon found in: {icon_candidates}")
        return False

def set_app_icon_delayed(app, logger=None):
    """
    Set application icon with delay to ensure main window is created
    
    Note: This function is now a no-op as WebGUI handles its own delayed icon setup
    to prevent duplicate icon refresh operations that cause window flashing.
    """
    # WebGUI._setup_windows_taskbar_icon_delayed() will handle this
    # Removing duplicate calls to prevent window flashing during login
    if logger:
        logger.debug("set_app_icon_delayed: Skipped (WebGUI handles its own icon setup)")
    pass