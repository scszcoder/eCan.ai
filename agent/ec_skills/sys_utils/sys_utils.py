from config.envi import getECBotDataHome

from pynput.mouse import Controller
import sys
from utils.logger_helper import logger_helper as logger

symTab = globals()

mouse = Controller()

mission_vars = []
# global function_table
MAX_STEPS = 1000000000
page_stack = []
current_context = None

screen_loc = (0, 0)

DEFAULT_RUN_STATUS = "Completed:0"


ecb_data_homepath = getECBotDataHome()


#####################################################################################
#  some useful utility functions
#####################################################################################
def getScreenSize():
    """
    Get accurate screen size across different platforms

    Returns:
        tuple: (width, height) of the primary screen
    """
    try:
        if sys.platform == 'win32':
            # Windows: Get accurate physical resolution handling DPI scaling
            try:
                # Method 1: Try to get actual resolution using EnumDisplaySettings
                try:
                    import win32api
                    import win32con

                    # Get primary display device
                    device = win32api.EnumDisplayDevices()
                    if device:
                        # Get current display settings for actual resolution
                        settings = win32api.EnumDisplaySettings(device.DeviceName, win32con.ENUM_CURRENT_SETTINGS)
                        if settings:
                            width = settings.PelsWidth
                            height = settings.PelsHeight
                            logger.info(f"getScreenSize (Windows actual): {width}x{height}")
                            return (width, height)
                except:
                    pass

                # Method 2: Try DPI-aware GetSystemMetrics
                try:
                    import ctypes
                    from ctypes import wintypes

                    # Set process DPI awareness to get real resolution
                    try:
                        # Try Windows 8.1+ method first
                        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
                    except:
                        try:
                            # Fallback to Windows Vista+ method
                            ctypes.windll.user32.SetProcessDPIAware()
                        except:
                            pass

                    # Get screen dimensions
                    user32 = ctypes.windll.user32
                    width = user32.GetSystemMetrics(0)  # SM_CXSCREEN
                    height = user32.GetSystemMetrics(1)  # SM_CYSCREEN

                    if width > 0 and height > 0:
                        logger.info(f"getScreenSize (Windows DPI aware): {width}x{height}")
                        return (width, height)
                except:
                    pass

                # Method 3: Fallback to basic win32api
                try:
                    import win32api
                    width = win32api.GetSystemMetrics(0)  # SM_CXSCREEN
                    height = win32api.GetSystemMetrics(1)  # SM_CYSCREEN
                    logger.info(f"getScreenSize (Windows basic): {width}x{height}")
                    return (width, height)
                except ImportError:
                    pass

            except Exception as e:
                logger.warning(f"Windows screen size detection failed: {e}")
                pass
        elif sys.platform == 'darwin':
            # macOS: Get accurate physical pixel resolution
            try:
                from Quartz import (
                    CGDisplayBounds, CGMainDisplayID, CGDisplayCopyDisplayMode,
                    CGDisplayModeGetPixelWidth, CGDisplayModeGetPixelHeight,
                    CGDisplayModeGetWidth, CGDisplayModeGetHeight
                )

                main_display = CGMainDisplayID()

                # Method 1: Get actual pixel dimensions from display mode (most accurate)
                try:
                    mode = CGDisplayCopyDisplayMode(main_display)
                    if mode:
                        # Try to get pixel dimensions (for Retina displays)
                        try:
                            pixel_width = CGDisplayModeGetPixelWidth(mode)
                            pixel_height = CGDisplayModeGetPixelHeight(mode)
                            if pixel_width > 0 and pixel_height > 0:
                                logger.info(f"getScreenSize (macOS pixel): {pixel_width}x{pixel_height}")
                                return (pixel_width, pixel_height)
                        except:
                            # Fallback to mode dimensions
                            width = CGDisplayModeGetWidth(mode)
                            height = CGDisplayModeGetHeight(mode)
                            if width > 0 and height > 0:
                                logger.info(f"getScreenSize (macOS mode): {width}x{height}")
                                return (width, height)
                except:
                    pass

                # Method 2: Use AppKit with scale factor calculation
                try:
                    from AppKit import NSScreen
                    screens = NSScreen.screens()
                    if screens:
                        main_screen = screens[0]
                        scale_factor = main_screen.backingScaleFactor()
                        frame = main_screen.frame()
                        # Calculate physical pixel dimensions
                        width = int(frame.size.width * scale_factor)
                        height = int(frame.size.height * scale_factor)
                        logger.info(f"getScreenSize (macOS AppKit): {width}x{height}")
                        return (width, height)
                except:
                    pass

                # Method 3: Fallback to bounds (logical resolution)
                bounds = CGDisplayBounds(main_display)
                width = int(bounds.size.width)
                height = int(bounds.size.height)
                logger.info(f"getScreenSize (macOS bounds): {width}x{height}")
                return (width, height)

            except ImportError:
                # If Quartz is not available, try AppKit only
                try:
                    from AppKit import NSScreen
                    screens = NSScreen.screens()
                    if screens:
                        main_screen = screens[0]
                        try:
                            scale_factor = main_screen.backingScaleFactor()
                            frame = main_screen.frame()
                            width = int(frame.size.width * scale_factor)
                            height = int(frame.size.height * scale_factor)
                            logger.info(f"getScreenSize (macOS AppKit only): {width}x{height}")
                            return (width, height)
                        except:
                            frame = main_screen.frame()
                            width = int(frame.size.width)
                            height = int(frame.size.height)
                            logger.info(f"getScreenSize (macOS AppKit logical): {width}x{height}")
                            return (width, height)
                except ImportError:
                    pass
        elif sys.platform.startswith('linux'):
            # Linux: Try to use xrandr or other methods
            try:
                import subprocess
                result = subprocess.run(['xrandr'], capture_output=True, text=True)
                if result.returncode == 0:
                    lines = result.stdout.split('\n')
                    for line in lines:
                        if ' connected primary ' in line or (' connected ' in line and 'primary' in line):
                            # Parse resolution from line like "1920x1080+0+0"
                            import re
                            match = re.search(r'(\d+)x(\d+)', line)
                            if match:
                                width = int(match.group(1))
                                height = int(match.group(2))
                                logger.info(f"getScreenSize: {width}x{height}")
                                return (width, height)
            except (ImportError, subprocess.SubprocessError, FileNotFoundError):
                # Fallback to pyautogui if xrandr not available
                pass

        # Fallback to pyautogui for all platforms
        return lazy.pyautogui.size()

    except Exception as e:
        # Ultimate fallback - return a reasonable default
        logger.error(f"Warning: Could not determine screen size, using default. Error: {e}")
        return (1920, 1080)


def get_default_download_dir():
    home = os.path.expanduser("~").replace("\\", "/")
    return home+"/Downloads/"