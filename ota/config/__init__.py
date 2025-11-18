"""
OTA Configuration Module
Unified configuration system using YAML
"""

from .loader import (
    OTAConfig,
    get_ota_config,
    is_ota_enabled,
    ota_config,
    validate_config,
)

__all__ = [
    'OTAConfig',
    'get_ota_config',
    'is_ota_enabled',
    'ota_config',  # Global instance for backward compatibility
    'validate_config',
]
