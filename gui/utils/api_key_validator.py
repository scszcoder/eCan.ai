"""
API Key Validation Utilities

This module provides centralized API key validation logic based on configuration.
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from utils.logger_helper import logger_helper as logger


class APIKeyValidator:
    """Centralized API key validation based on configuration"""
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize the validator with configuration
        
        Args:
            config_path: Path to validation configuration file
        """
        if config_path is None:
            # Default to config file in gui/config directory
            current_dir = Path(__file__).parent.parent
            config_path = current_dir / "config" / "api_key_validation.json"
        
        self.config_path = Path(config_path)
        self._config = self._load_config()
    
    def _load_config(self) -> Dict:
        """Load validation configuration from JSON file"""
        try:
            if not self.config_path.exists():
                logger.warning(f"API key validation config not found: {self.config_path}")
                return self._get_default_config()
            
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                logger.debug(f"Loaded API key validation config from {self.config_path}")
                return config
                
        except Exception as e:
            logger.error(f"Failed to load API key validation config: {e}")
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict:
        """Get default configuration if file loading fails"""
        return {
            "validation_rules": {},
            "patterns": {
                "api_key_suffixes": ["_API_KEY", "_KEY", "_TOKEN", "_SECRET", "_PASSWORD"],
                "special_variables": ["AZURE_ENDPOINT", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"],
                "orphaned_patterns": ["VSCODE_DEBUGPY_ADAPTER_ENDPOINTS"]
            },
            "masking": {
                "show_prefix_chars": 8,
                "show_suffix_chars": 4,
                "min_length_for_masking": 12,
                "fallback_prefix_chars": 4
            }
        }
    
    def validate_api_key(self, env_var: str, api_key: str) -> Tuple[bool, Optional[str]]:
        """
        Validate API key format for specific environment variable
        
        Args:
            env_var: Environment variable name
            api_key: API key to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not api_key or not api_key.strip():
            return False, "API key cannot be empty"
        
        api_key = api_key.strip()
        
        # Get validation rules for this environment variable
        rules = self._config.get("validation_rules", {}).get(env_var, {})
        
        if not rules:
            # No specific rules, just check minimum length
            if len(api_key) < 10:
                return False, f"{env_var} is too short"
            return True, None
        
        # Check prefix requirement
        if "prefix" in rules:
            if not api_key.startswith(rules["prefix"]):
                description = rules.get("description", f"{env_var}")
                return False, f"{description} should start with '{rules['prefix']}'"
        
        # Check minimum length
        min_length = rules.get("min_length", 10)
        if len(api_key) < min_length:
            description = rules.get("description", f"{env_var}")
            return False, f"{description} is too short (minimum {min_length} characters)"
        
        return True, None
    
    def mask_api_key(self, api_key: str) -> str:
        """
        Mask API key for safe logging
        
        Args:
            api_key: API key to mask
            
        Returns:
            Masked API key string
        """
        if not api_key:
            return "***"
        
        masking_config = self._config.get("masking", {})
        min_length = masking_config.get("min_length_for_masking", 12)
        prefix_chars = masking_config.get("show_prefix_chars", 8)
        suffix_chars = masking_config.get("show_suffix_chars", 4)
        fallback_chars = masking_config.get("fallback_prefix_chars", 4)
        
        if len(api_key) >= min_length:
            return f"{api_key[:prefix_chars]}...{api_key[-suffix_chars:]}"
        else:
            return f"{api_key[:fallback_chars]}..."
    
    def is_api_key_variable(self, env_var: str) -> bool:
        """
        Check if environment variable is an API key variable
        
        Args:
            env_var: Environment variable name
            
        Returns:
            True if it's an API key variable
        """
        patterns = self._config.get("patterns", {})
        
        # Check suffixes
        suffixes = patterns.get("api_key_suffixes", [])
        if any(env_var.upper().endswith(suffix) for suffix in suffixes):
            return True
        
        # Check special variables
        special_vars = patterns.get("special_variables", [])
        if env_var in special_vars:
            return True
        
        return False
    
    def get_orphaned_patterns(self) -> List[str]:
        """Get list of orphaned variable patterns to clean up"""
        return self._config.get("patterns", {}).get("orphaned_patterns", [])
    
    def get_api_key_patterns(self) -> List[str]:
        """Get list of API key patterns for matching"""
        return self._config.get("patterns", {}).get("api_key_suffixes", [])


# Global validator instance
_validator_instance = None

def get_api_key_validator() -> APIKeyValidator:
    """Get global API key validator instance"""
    global _validator_instance
    if _validator_instance is None:
        _validator_instance = APIKeyValidator()
    return _validator_instance
