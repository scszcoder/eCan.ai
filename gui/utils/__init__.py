# -*- coding: utf-8 -*-
"""
Utilities module for eCan GUI

This module contains utility classes and functions.
"""

from .hardware_detector import HardwareDetector, get_hardware_detector
from .system_info import (
    SystemInfoManager, 
    get_system_info_manager,
    get_friendly_machine_name,
    get_device_type,
    get_system_architecture,
    get_processor_info,
    get_memory_info,
    get_system_performance,
    get_complete_system_info
)

__all__ = [
    'HardwareDetector',
    'get_hardware_detector',
    'SystemInfoManager',
    'get_system_info_manager',
    'get_friendly_machine_name',
    'get_device_type',
    'get_system_architecture',
    'get_processor_info',
    'get_memory_info',
    'get_system_performance',
    'get_complete_system_info'
]
