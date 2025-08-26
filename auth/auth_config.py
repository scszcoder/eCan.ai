"""
Simple Authentication Configuration
Direct YAML mapping with AuthConfig.xx.xxx access pattern
"""
import yaml
from pathlib import Path
from typing import Any

class ConfigNamespace:
    """Dynamic namespace for accessing config sections"""
    
    def __init__(self, config_dict: dict):
        self._config = config_dict
    
    def __getattr__(self, name: str) -> Any:
        """Direct access to config values"""
        if name in self._config:
            return self._config[name]
        raise AttributeError(f"Configuration key '{name}' not found")

class AuthConfig:
    """Direct YAML configuration access"""
    
    _instance = None
    _config = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._load_config()
        return cls._instance
    
    @classmethod
    def _load_config(cls):
        """Load configuration from auth_config.yml"""
        config_path = Path(__file__).parent / "auth_config.yml"
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                cls._config = yaml.safe_load(f) or {}
        except Exception as e:
            print(f"Error: Failed to load auth_config.yml: {e}")
            cls._config = {}
    
    def __getattr__(self, name: str) -> Any:
        """Enable AuthConfig.COGNITO.xxx access pattern"""
        if name in self._config:
            if isinstance(self._config[name], dict):
                return ConfigNamespace(self._config[name])
            return self._config[name]
        raise AttributeError(f"Configuration section '{name}' not found")

# Create global instance
AuthConfig = AuthConfig()
