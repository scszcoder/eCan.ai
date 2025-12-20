"""
eCan OTA (Over-The-Air) Update Package

Self-contained cross-platform automatic update system, supporting:
- macOS (native PKG installer with privilege elevation)
- Windows (native EXE/MSI installer with silent mode)
- Linux (generic HTTP-based updater)

Uses Sparkle-compatible appcast XML format but with independent implementation.
No external OTA framework dependencies required.
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