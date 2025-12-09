# GUI Manager Module
# This module contains various managers for GUI components

"""
GUI Manager Module - GUI Manager Module

Simplified configuration management system providing ORM-style configuration management.

Main Components:
- ConfigManager: Core configuration manager
- Settings: Settings entity class (corresponds to settings.json)
- AdsSettings: ADS settings entity class
- SearchSettings: Search settings entity class

Usage Example:
    from gui.manager import ConfigManager

    config_manager = ConfigManager(user_data_path)

    # Use ORM-style operations
    config_manager.settings.debug_mode = True
    config_manager.settings.save()

    # Or directly operate JSON
    vehicles = config_manager.get_vehicles()
"""

# Import main classes
from .config_manager import ConfigManager
from .browser_manager import BrowserManager, AutoBrowser, BrowserType, BrowserStatus
from gui.config.general_settings import GeneralSettings
from gui.config.ads_settings import AdsSettings
from gui.config.search_settings import SearchSettings
from gui.utils.hardware_detector import HardwareDetector, get_hardware_detector

# Exported public interface
__all__ = [
    'ConfigManager',
    'BrowserManager',
    'AutoBrowser',
    'BrowserType',
    'BrowserStatus',
    'GeneralSettings',
    'AdsSettings',
    'SearchSettings',
    'HardwareDetector',
    'get_hardware_detector'
]

# Version information
__version__ = '2.0.0'
__author__ = 'eCan.ai Team'
