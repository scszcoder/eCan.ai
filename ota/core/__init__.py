"""
OTA Core Module
Contains update manager, platform adapters and other core components
"""

from .updater import OTAUpdater
from .platforms import SparkleUpdater, WinSparkleUpdater, GenericUpdater

__all__ = [
    "OTAUpdater",
    "SparkleUpdater", 
    "WinSparkleUpdater",
    "GenericUpdater"
] 