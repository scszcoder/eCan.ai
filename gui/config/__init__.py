# -*- coding: utf-8 -*-
"""
Configuration module for eCan GUI

This module contains all configuration-related classes and utilities.
"""

from .general_settings import GeneralSettings
from .ads_settings import AdsSettings  
from .search_settings import SearchSettings

__all__ = [
    'GeneralSettings',
    'AdsSettings', 
    'SearchSettings'
]
