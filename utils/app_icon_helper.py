import os
import sys
from PySide6.QtGui import QIcon
from config.app_info import app_info

def set_app_icon(app, logger=None):
    """
    根据当前平台自动查找并设置应用程序图标。
    支持 macOS（Dock）、Windows（任务栏）、其它平台。
    可选 logger 记录加载结果。
    """
    # 使用绝对路径，基于app_info.app_resources_path
    resource_path = app_info.app_resources_path

    if sys.platform == 'darwin':
        icon_candidates = [
            os.path.join(resource_path, "images", "logos", "rounded", "dock_512x512.png"),
            os.path.join(resource_path, "images", "logos", "rounded", "dock_256x256.png"),
            os.path.join(resource_path, "images", "logos", "rounded", "dock_128x128.png"),
            # os.path.join(resource_path, "images", "logos", "dock_512x512.png"),
            # os.path.join(resource_path, "images", "logos", "dock_256x256.png"),
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

    icon_path = None
    for candidate in icon_candidates:
        if os.path.exists(candidate):
            icon_path = candidate
            break

    if icon_path:
        print(f"实际加载的图标: {icon_path}")
        app_icon = QIcon(icon_path)
        app.setWindowIcon(app_icon)
        if logger:
            logger.info(f"Successfully loaded application icon from: {icon_path}")
    else:
        print(f"未找到可用的应用图标，候选: {icon_candidates}")
        if logger:
            logger.error(f"Warning: Could not find any application icon in: {icon_candidates}") 