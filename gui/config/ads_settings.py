#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ADS Settings Entity - ADS settings entity class
"""

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gui.manager.config_manager import ConfigManager


class AdsSettings:
    """ADS settings entity class"""

    def __init__(self, config_manager: 'ConfigManager'):
        """
        Initialize ADS settings entity

        Args:
            config_manager: Configuration manager instance
        """
        self.config_manager = config_manager
        self.settings_file = os.path.join(config_manager.user_data_path, 'ads_profiles/ads_settings.json')

        # Load settings
        self._data = self._load_settings()

    def _load_settings(self) -> dict:
        """Load ADS settings data"""
        default_settings = {
            "user name": "",
            "user pwd": "",
            "batch_size": 2,
            "batch_method": "min batches",
            "ads_port": 50325,
            "ads_api_key": "",
            "ads_profile_dir": "",
            "default_scraper_email": "abc@gmail.com",
            "chrome_version": "92",
            "chromedriver_lut": {
                "92": "chromedriver-win32/v92.0.4515.107/chromedriver.exe",
                "120": "chromedriver-win64/v120.0.6099.62/chromedriver.exe",
                "128": "chromedriver-win64/v128.0.6613.84/chromedriver.exe"
            },
            "chromedriver": "chromedriver-win64/v128.0.6613.84/chromedriver.exe"
        }
        
        return self.config_manager.load_json(self.settings_file, default_settings)
        
    def save(self) -> bool:
        """Save settings"""
        return self.config_manager.save_json(self.settings_file, self._data)

    def reload(self):
        """Reload settings"""
        self._data = self._load_settings()

    @property
    def data(self) -> dict:
        """Get settings data dictionary"""
        return self._data

    # ==================== User Credentials ====================
    
    @property
    def user_name(self) -> str:
        """ADS username"""
        return self._data.get("user name", "")

    @user_name.setter
    def user_name(self, value: str):
        self._data["user name"] = value

    @property
    def user_pwd(self) -> str:
        """ADS password"""
        return self._data.get("user pwd", "")

    @user_pwd.setter
    def user_pwd(self, value: str):
        self._data["user pwd"] = value

    # ==================== Batch Settings ====================
    
    @property
    def batch_size(self) -> int:
        """Batch size"""
        return self._data.get("batch_size", 2)

    @batch_size.setter
    def batch_size(self, value: int):
        self._data["batch_size"] = value

    @property
    def batch_method(self) -> str:
        """Batch method: min batches, max batches"""
        return self._data.get("batch_method", "min batches")

    @batch_method.setter
    def batch_method(self, value: str):
        self._data["batch_method"] = value

    # ==================== API Settings ====================
    
    @property
    def ads_port(self) -> int:
        """ADS port"""
        return self._data.get("ads_port", 50325)

    @ads_port.setter
    def ads_port(self, value: int):
        self._data["ads_port"] = value

    @property
    def ads_api_key(self) -> str:
        """ADS API key"""
        return self._data.get("ads_api_key", "")

    @ads_api_key.setter
    def ads_api_key(self, value: str):
        self._data["ads_api_key"] = value

    @property
    def ads_profile_dir(self) -> str:
        """ADS profile directory"""
        return self._data.get("ads_profile_dir", "")

    @ads_profile_dir.setter
    def ads_profile_dir(self, value: str):
        self._data["ads_profile_dir"] = value


    @property
    def chrome_version(self) -> str:
        """ADS profile directory"""
        return self._data.get("chrome_version", "")

    @chrome_version.setter
    def chrome_version(self, value: str):
        self._data["chrome_version"] = value


    @property
    def chromedriver_lut(self) -> str:
        """ADS profile directory"""
        return self._data.get("chromedriver_lut", "")

    @chromedriver_lut.setter
    def chromedriver_lut(self, value: str):
        self._data["chromedriver_lut"] = value

    @property
    def chromedriver(self) -> str:
        """ADS profile directory"""
        return self._data.get("chromedriver", "")

    @chromedriver.setter
    def chromedriver(self, value: str):
        self._data["chromedriver"] = value


    @property
    def default_scraper_email(self) -> str:
        """ADS profile directory"""
        return self._data.get("default_scraper_email", "")

    @default_scraper_email.setter
    def default_scraper_email(self, value: str):
        self._data["default_scraper_email"] = value

    # ==================== Convenience Methods ====================
    
    def get_all_data(self) -> dict:
        """Get all ADS settings data"""
        return self._data.copy()

    def update_data(self, data: dict):
        """Batch update ADS settings data"""
        self._data.update(data)

    def is_configured(self) -> bool:
        """Check if ADS is configured"""
        return bool(self.user_name and self.user_pwd)
