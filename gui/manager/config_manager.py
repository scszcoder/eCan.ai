#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Configuration Manager - Simplified configuration manager
Responsible for managing application configuration information
"""

import json
import os
from typing import Any
from utils.logger_helper import logger_helper as logger


class ConfigManager:
    """
    Simplified configuration manager
    Responsible for managing all application configuration files
    """

    def __init__(self, user_data_path: str):
        """
        Initialize configuration manager

        Args:
            user_data_path: User data path
        """
        self.user_data_path = user_data_path

        # Ensure necessary directories exist
        self._ensure_directories()

        logger.info(f"ConfigManager initialized: {user_data_path}")

    def _ensure_directories(self):
        """Ensure necessary directories exist"""
        directories = [
            os.path.join(self.user_data_path, 'resource/data'),
            os.path.join(self.user_data_path, 'ads_profiles'),
        ]

        for directory in directories:
            os.makedirs(directory, exist_ok=True)

    def load_json(self, file_path: str, default_value: Any = None) -> Any:
        """
        Load JSON file

        Args:
            file_path: File path
            default_value: Default value

        Returns:
            Loaded data or default value
        """
        try:
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                logger.debug(f"Loaded config: {file_path}")
                return data
            else:
                logger.info(f"Config file not found, using default: {file_path}")
                return default_value if default_value is not None else {}

        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error in {file_path}: {e}")
            return default_value if default_value is not None else {}
        except Exception as e:
            logger.error(f"Error loading {file_path}: {e}")
            return default_value if default_value is not None else {}



    def save_json(self, file_path: str, data: Any) -> bool:
        """
        Save JSON file with permission error handling

        Args:
            file_path: File path
            data: Data to save

        Returns:
            Whether save was successful
        """
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(file_path), exist_ok=True)

            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)

            logger.debug(f"Saved config: {file_path}")
            return True

        except PermissionError as e:
            logger.error(f"Permission denied saving {file_path}: {e}")
            logger.error("Unable to save settings due to permission issues.")
            logger.error("Please check directory permissions or run the application with appropriate privileges.")
            return False

        except Exception as e:
            logger.error(f"Error saving {file_path}: {e}")
            return False



    @property
    def general_settings(self):
        """General settings entity"""
        if not hasattr(self, '_general_settings'):
            from gui.config.general_settings import GeneralSettings
            self._general_settings = GeneralSettings(self)
        return self._general_settings

    @property
    def ads_settings(self):
        """ADS settings entity"""
        if not hasattr(self, '_ads_settings'):
            from gui.config.ads_settings import AdsSettings
            self._ads_settings = AdsSettings(self)
        return self._ads_settings

    @property
    def search_settings(self):
        """Search settings entity"""
        if not hasattr(self, '_search_settings'):
            from gui.config.search_settings import SearchSettings
            self._search_settings = SearchSettings(self)
        return self._search_settings

    @property
    def llm_manager(self):
        """LLM manager entity"""
        if not hasattr(self, '_llm_manager'):
            from gui.manager.llm_manager import LLMManager
            self._llm_manager = LLMManager(self)
        return self._llm_manager

    @property
    def embedding_manager(self):
        """Embedding manager entity"""
        if not hasattr(self, '_embedding_manager'):
            from gui.manager.embedding_manager import EmbeddingManager
            self._embedding_manager = EmbeddingManager(self)
        return self._embedding_manager

    @property
    def rerank_manager(self):
        """Rerank manager entity"""
        if not hasattr(self, '_rerank_manager'):
            from gui.manager.rerank_manager import RerankManager
            self._rerank_manager = RerankManager(self)
        return self._rerank_manager

    def save_all_settings(self) -> bool:
        """Save all settings"""
        try:
            success = True
            success &= self.general_settings.save()
            success &= self.ads_settings.save()
            success &= self.search_settings.save()

            if success:
                logger.info("All settings saved successfully")
            else:
                logger.error("Failed to save some settings")
            return success
        except Exception as e:
            logger.error(f"Error saving all settings: {e}")
            return False

    def get_log_settings(self) -> dict:
        """Get log settings"""
        log_file = os.path.join(self.user_data_path, 'resource/data/log_settings.json')
        return self.load_json(log_file, {})

    def save_log_settings(self, settings: dict) -> bool:
        """Save log settings"""
        log_file = os.path.join(self.user_data_path, 'resource/data/log_settings.json')
        return self.save_json(log_file, settings)

    def get_vehicles(self) -> list:
        """Get vehicle configuration"""
        vehicles_file = os.path.join(self.user_data_path, 'vehicles.json')
        return self.load_json(vehicles_file, [])

    def save_vehicles(self, vehicles: list) -> bool:
        """Save vehicle configuration"""
        vehicles_file = os.path.join(self.user_data_path, 'vehicles.json')
        return self.save_json(vehicles_file, vehicles)

    def get_product_catalog(self) -> dict:
        """Get product catalog"""
        catalog_file = os.path.join(self.user_data_path, 'resource/data/product_catelog.json')
        return self.load_json(catalog_file, {})

    def save_product_catalog(self, catalog: dict) -> bool:
        """Save product catalog"""
        catalog_file = os.path.join(self.user_data_path, 'resource/data/product_catelog.json')
        return self.save_json(catalog_file, catalog)