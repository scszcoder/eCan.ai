"""
ECBot OTA (Over-The-Air) Update Package

Provides cross-platform automatic update functionality, supporting:
- macOS (Sparkle)
- Windows (winSparkle) 
- Linux (Generic HTTP API)
"""

from .core.updater import OTAUpdater
# Lazy import GUI components to avoid hard dependency at import time

def __getattr__(name):
    if name in ("UpdateDialog", "UpdateNotificationDialog"):
        from .gui.dialog import UpdateDialog, UpdateNotificationDialog
        return {"UpdateDialog": UpdateDialog, "UpdateNotificationDialog": UpdateNotificationDialog}[name]
    raise AttributeError(f"module 'ota' has no attribute {name!r}")

__version__ = "1.0.0"
__all__ = [
    "OTAUpdater",
    "UpdateDialog", 
    "UpdateNotificationDialog"
] 