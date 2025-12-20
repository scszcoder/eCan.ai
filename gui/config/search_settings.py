#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Search Settings Entity - Search settings entity class
"""

import os
from typing import Dict, List, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from gui.manager.config_manager import ConfigManager


class SearchSettings:
    """Search settings entity class"""

    def __init__(self, config_manager: 'ConfigManager'):
        """
        Initialize search settings entity

        Args:
            config_manager: Configuration manager instance
        """
        self.config_manager = config_manager
        self.settings_file = os.path.join(config_manager.user_data_path, 'resource/data/search_settings.json')

        # Load settings
        self._data = self._load_settings()

    def _load_settings(self) -> dict:
        """Load search settings data"""
        default_settings = {
            "search_terms": {
                "amz": {}
            },
            "selType_selections": ["st", "sp", "ac", "ch"],
            "detailLvl_selections": [0, 1, 2, 3],
            "flow_selections": ["normal", "fast", "detailed"],
            "max_browse_products_per_page": 5,
            "max_browse_pages": 3,
            "max_searches": 2
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

    # ==================== Search Terms Settings ====================
    
    @property
    def search_terms(self) -> Dict[str, Any]:
        """Search terms configuration"""
        return self._data.get("search_terms", {"amz": {}})

    @search_terms.setter
    def search_terms(self, value: Dict[str, Any]):
        self._data["search_terms"] = value

    def get_amz_search_terms(self) -> Dict[str, Any]:
        """Get Amazon search terms"""
        return self.search_terms.get("amz", {})

    def set_amz_search_terms(self, terms: Dict[str, Any]):
        """Set Amazon search terms"""
        if "search_terms" not in self._data:
            self._data["search_terms"] = {}
        self._data["search_terms"]["amz"] = terms

    # ==================== Selection Settings ====================
    
    @property
    def sel_type_selections(self) -> List[str]:
        """Selection type"""
        return self._data.get("selType_selections", ["st", "sp", "ac", "ch"])

    @sel_type_selections.setter
    def sel_type_selections(self, value: List[str]):
        self._data["selType_selections"] = value

    @property
    def detail_lvl_selections(self) -> List[int]:
        """Detail level selections"""
        return self._data.get("detailLvl_selections", [0, 1, 2, 3])

    @detail_lvl_selections.setter
    def detail_lvl_selections(self, value: List[int]):
        self._data["detailLvl_selections"] = value

    @property
    def flow_selections(self) -> List[str]:
        """Flow selections"""
        return self._data.get("flow_selections", ["normal", "fast", "detailed"])

    @flow_selections.setter
    def flow_selections(self, value: List[str]):
        self._data["flow_selections"] = value

    # ==================== Browse Limit Settings ====================
    
    @property
    def max_browse_products_per_page(self) -> int:
        """Maximum browse products per page"""
        return self._data.get("max_browse_products_per_page", 5)

    @max_browse_products_per_page.setter
    def max_browse_products_per_page(self, value: int):
        self._data["max_browse_products_per_page"] = value

    @property
    def max_browse_pages(self) -> int:
        """Maximum browse pages"""
        return self._data.get("max_browse_pages", 3)

    @max_browse_pages.setter
    def max_browse_pages(self, value: int):
        self._data["max_browse_pages"] = value

    @property
    def max_searches(self) -> int:
        """Maximum searches"""
        return self._data.get("max_searches", 2)

    @max_searches.setter
    def max_searches(self, value: int):
        self._data["max_searches"] = value

    # ==================== Convenience Methods ====================
    
    def get_all_data(self) -> dict:
        """Get all search settings data"""
        return self._data.copy()

    def update_data(self, data: dict):
        """Batch update search settings data"""
        self._data.update(data)

    def add_search_term_category(self, platform: str, category: str, terms: List[str]):
        """Add search term category"""
        if "search_terms" not in self._data:
            self._data["search_terms"] = {}
        if platform not in self._data["search_terms"]:
            self._data["search_terms"][platform] = {}
        self._data["search_terms"][platform][category] = terms

    def get_search_term_category(self, platform: str, category: str) -> List[str]:
        """Get search term category"""
        return self._data.get("search_terms", {}).get(platform, {}).get(category, [])
