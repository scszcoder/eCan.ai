"""
OTA Core Module
Contains update manager, platform adapters and other core components
"""

from .updater import OTAUpdater
from .platforms import MacOSUpdater, WindowsUpdater, GenericUpdater

__all__ = [
    "OTAUpdater",
    "MacOSUpdater", 
    "WindowsUpdater",
    "GenericUpdater"
] 