import os
import sys
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication
from config.app_info import app_info

# Windows 特定导入
if sys.platform == 'win32':
    try:
        import ctypes
    except ImportError:
        ctypes = None

# macOS 特定导入
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
    统一设置应用程序基本信息
    包括名称、版本、组织信息等
    """
    if not app:
        if logger:
            logger.error("QApplication instance is required")
        return False
    
    try:
        # 基本应用程序信息
        app.setApplicationName("eCan")
        app.setApplicationDisplayName("eCan")
        app.setOrganizationName("eCan Team")
        app.setOrganizationDomain("ecan.app")
        
        # 读取版本信息
        version = "1.0.0"
        try:
            # 尝试多个可能的VERSION文件位置
            version_paths = [
                "VERSION",  # 当前目录
                os.path.join(os.path.dirname(__file__), "..", "VERSION"),  # 项目根目录
                os.path.join(os.getcwd(), "VERSION"),  # 工作目录
            ]
            
            for version_path in version_paths:
                if os.path.exists(version_path):
                    with open(version_path, "r", encoding="utf-8") as f:
                        version = f.read().strip()
                    break
        except Exception as e:
            if logger:
                logger.warning(f"读取VERSION文件失败: {e}")
            pass
        
        app.setApplicationVersion(version)
        
        if logger:
            logger.info(f"应用程序信息设置完成: eCan v{version}")
        
        # 平台特定设置
        if sys.platform == 'darwin':
            _setup_macos_app_info(app, logger)
        elif sys.platform == 'win32':
            _setup_windows_app_info(app, logger)
        
        return True
        
    except Exception as e:
        if logger:
            logger.error(f"设置应用程序信息失败: {e}")
        return False

def _setup_macos_app_info(app, logger=None):
    """设置macOS特定的应用程序信息"""
    try:
        # 设置进程名称
        if setproctitle:
            setproctitle("eCan")
            if logger:
                logger.info("macOS进程名称设置为: eCan")
        
        # 设置macOS原生应用程序信息
        if Foundation and AppKit:
            try:
                # 获取当前应用程序
                ns_app = AppKit.NSApplication.sharedApplication()
                
                # 设置应用程序激活策略，确保正确显示在Dock中
                ns_app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyRegular)
                
                # 创建虚拟的bundle信息
                bundle_info = {
                    'CFBundleName': 'eCan',
                    'CFBundleDisplayName': 'eCan',
                    'CFBundleIdentifier': 'com.ecan.app',
                    'CFBundleVersion': app.applicationVersion(),
                    'CFBundleShortVersionString': app.applicationVersion()
                }
                
                # 尝试设置bundle信息
                bundle = Foundation.NSBundle.mainBundle()
                if bundle:
                    info_dict = bundle.infoDictionary()
                    if info_dict:
                        for key, value in bundle_info.items():
                            info_dict[key] = value
                
                # 确保应用程序名称正确设置
                # 这有助于避免菜单重复问题
                if hasattr(ns_app, 'setApplicationIconImage_'):
                    # 如果有图标，设置应用程序图标
                    pass
                
                if logger:
                    logger.info("macOS原生应用程序信息设置完成")
                    
            except Exception as e:
                if logger:
                    logger.warning(f"macOS原生应用程序信息设置失败: {e}")
        
    except Exception as e:
        if logger:
            logger.warning(f"macOS应用程序信息设置失败: {e}")

def _setup_windows_app_info(app, logger=None):
    """设置Windows特定的应用程序信息"""
    try:
        if sys.platform == 'win32' and ctypes:
            # 设置应用程序用户模型 ID
            app_id = "eCan.AI.App"
            shell32 = ctypes.windll.shell32
            shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
            
            if logger:
                logger.info(f"Windows应用程序ID设置为: {app_id}")
                
    except Exception as e:
        if logger:
            logger.warning(f"Windows应用程序信息设置失败: {e}")

def set_windows_taskbar_icon(app, icon_path, logger=None):
    """
    Windows 特定的任务栏图标设置
    """
    if sys.platform != 'win32' or not ctypes or not icon_path:
        return False

    try:
        print(f"[DEBUG] Setting Windows taskbar icon: {icon_path}")

        # 方法1: 设置应用程序用户模型 ID (AppUserModelID)
        app_id = "eCan.AI.App"
        shell32 = ctypes.windll.shell32
        shell32.SetCurrentProcessExplicitAppUserModelID(app_id)

        # 方法2: 清除图标缓存并强制刷新
        try:
            # 获取主窗口句柄
            main_window = app.activeWindow()
            if main_window:
                hwnd = int(main_window.winId())
                user32 = ctypes.windll.user32

                # 如果是 .ico 文件，尝试直接设置
                if icon_path.endswith('.ico') and os.path.exists(icon_path):
                    # 加载图标
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
                        # 设置大图标（任务栏）
                        user32.SendMessageW(hwnd, 0x0080, 1, hicon_large)  # WM_SETICON, ICON_LARGE
                        print(f"[DEBUG] Set large icon (32x32) for taskbar")

                    if hicon_small:
                        # 设置小图标（标题栏）
                        user32.SendMessageW(hwnd, 0x0080, 0, hicon_small)  # WM_SETICON, ICON_SMALL
                        print(f"[DEBUG] Set small icon (16x16) for title bar")

                    # 强制刷新任务栏
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
    清除 Windows 图标缓存（谨慎使用，会重启 Explorer）
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
    根据当前平台自动查找并设置应用程序图标。
    """
    resource_path = app_info.app_resources_path

    # 调试信息：打印实际使用的资源路径
    print(f"[DEBUG] Resource path: {resource_path}")
    if logger:
        logger.info(f"Using resource path: {resource_path}")

    # 根据平台选择图标候选列表
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

    # 查找第一个存在的图标文件
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
        # 设置应用图标
        app_icon = QIcon(icon_path)
        app.setWindowIcon(app_icon)

        # Windows 特定设置
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

        # 提供图标缓存清除的说明
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
    延迟设置应用图标，确保主窗口已经创建
    """
    from PySide6.QtCore import QTimer

    def delayed_setup():
        set_app_icon(app, logger)

    QTimer.singleShot(100, delayed_setup)