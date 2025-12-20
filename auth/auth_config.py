"""
Authentication Configuration
Centralized configuration management
"""
import yaml
from pathlib import Path
from typing import Any

class ConfigNamespace:
    """Dynamic namespace for accessing config sections"""
    
    def __init__(self, config_dict: dict):
        self._config = config_dict
    
    def __getattr__(self, name: str) -> Any:
        """Direct access to config values with nested dict support"""
        if name in self._config:
            value = self._config[name]
            # If value is a dict, wrap it in another ConfigNamespace for nested access
            if isinstance(value, dict):
                return ConfigNamespace(value)
            return value
        raise AttributeError(f"Configuration key '{name}' not found")

class AuthConfigMeta(type):
    """Metaclass for AuthConfig to enable class-level attribute access"""
    
    _config = None
    _loaded = False
    
    def __getattr__(cls, name: str) -> Any:
        """Enable AuthConfig.COGNITO.xxx class-level access pattern"""
        if not cls._loaded:
            cls._load_config()
        
        if name in cls._config:
            if isinstance(cls._config[name], dict):
                return ConfigNamespace(cls._config[name])
            return cls._config[name]
        raise AttributeError(f"Configuration section '{name}' not found")
    
    def _load_config(cls):
        """Load configuration from auth_config.yml"""
        config_path = Path(__file__).parent / "auth_config.yml"
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                cls._config = yaml.safe_load(f) or {}
            cls._loaded = True
        except Exception as e:
            print(f"Error: Failed to load auth_config.yml: {e}")
            cls._config = {}
            cls._loaded = True

class AuthConfig(metaclass=AuthConfigMeta):
    """Centralized authentication configuration with class-level access"""
    
    @classmethod
    def reload_config(cls):
        """Force reload configuration from file"""
        cls._loaded = False
        cls._load_config()
