"""
OTA核心功能模块
包含更新管理器、平台适配器等核心组件
"""

from .updater import OTAUpdater
from .platforms import SparkleUpdater, WinSparkleUpdater, GenericUpdater

__all__ = [
    "OTAUpdater",
    "SparkleUpdater", 
    "WinSparkleUpdater",
    "GenericUpdater"
] 