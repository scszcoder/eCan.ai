"""
ECBot OTA (Over-The-Air) Update Package

提供跨平台的自动更新功能，支持：
- macOS (Sparkle)
- Windows (winSparkle) 
- Linux (通用HTTP API)
"""

from .core.updater import OTAUpdater
from .gui.dialog import UpdateDialog, UpdateNotificationDialog

__version__ = "1.0.0"
__all__ = [
    "OTAUpdater",
    "UpdateDialog", 
    "UpdateNotificationDialog"
] 