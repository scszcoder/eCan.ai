"""
Authentication Configuration
Centralized configuration management

Supports dual-app: loads from apps/cn/config/auth_config.yml or
apps/intl/config/auth_config.yml based on ECAN_APP_ID env var.
"""
import os
import yaml
from pathlib import Path
from typing import Any

# Lazy import to avoid circular dependency
_app_config_loader = None


def _get_auth_config_path() -> Path:
    app_id = os.environ.get('ECAN_APP_ID', 'intl')
    project_root = Path(__file__).resolve().parent.parent
    app_config_path = project_root / 'apps' / app_id / 'config' / 'auth_config.yml'
    if app_config_path.exists():
        return app_config_path
    # Fallback to legacy location for dev compatibility
    return Path(__file__).parent / "auth_config.yml"


class ConfigNamespace:
    """Dynamic namespace for accessing config sections"""

    def __init__(self, config_dict: dict):
        self._config = config_dict

    def __getattr__(self, name: str) -> Any:
        """Direct access to config values with nested dict support"""
        if name in self._config:
            value = self._config[name]
            if isinstance(value, dict):
                return ConfigNamespace(value)
            return value
        raise AttributeError(f"Configuration key '{name}' not found")


class AuthConfigMeta(type):
    """Metaclass for AuthConfig to enable class-level attribute access"""

    _config = None
    _loaded = False
    _loaded_app_id = None

    def __getattr__(cls, name: str) -> Any:
        """Enable AuthConfig.COGNITO.xxx / AuthConfig.CAM.xxx class-level access"""
        current_app_id = os.environ.get('ECAN_APP_ID', 'intl')
        if not cls._loaded or cls._loaded_app_id != current_app_id:
            cls._load_config(current_app_id)

        if name in cls._config:
            if isinstance(cls._config[name], dict):
                return ConfigNamespace(cls._config[name])
            return cls._config[name]
        raise AttributeError(f"Configuration section '{name}' not found")

    def _load_config(cls, app_id: str):
        """Load configuration from apps/{app_id}/config/auth_config.yml.

        Fallback order:
        1. apps/{app_id}/config/auth_config.yml
        2. auth/auth_config.yml (legacy, contains real dev credentials)
        3. Environment variables (AWS_COGNITO_* etc.)
        """
        project_root = Path(__file__).resolve().parent.parent
        app_config_path = project_root / 'apps' / app_id / 'config' / 'auth_config.yml'
        legacy_config_path = Path(__file__).parent / "auth_config.yml"

        loaded = {}
        try:
            config_path = app_config_path if app_config_path.exists() else legacy_config_path
            with open(config_path, 'r', encoding='utf-8') as f:
                loaded = yaml.safe_load(f) or {}

            # For Intl app: if apps/intl/config/auth_config.yml has empty values
            # but legacy auth/auth_config.yml has real values, merge them.
            if app_id == 'intl' and app_config_path.exists() and legacy_config_path.exists():
                with open(legacy_config_path, 'r', encoding='utf-8') as f:
                    legacy = yaml.safe_load(f) or {}
                legacy_cognito = legacy.get('COGNITO', {})
                intl_cognito = loaded.get('COGNITO', {})
                # Fallback to legacy values when intl values are empty strings
                for key, val in legacy_cognito.items():
                    if intl_cognito.get(key) in (None, ''):
                        intl_cognito[key] = val
                loaded['COGNITO'] = intl_cognito

            # Final fallback: environment variables
            cls._apply_env_overrides(loaded)

            cls._config = loaded
            cls._loaded = True
            cls._loaded_app_id = app_id
        except Exception as e:
            print(f"Error: Failed to load auth_config.yml: {e}")
            cls._config = {}
            cls._loaded = True
            cls._loaded_app_id = app_id

    @staticmethod
    def _apply_env_overrides(config: dict):
        """Override empty string values with environment variables."""
        env_map = {
            'COGNITO': {
                'USER_POOL_ID': 'AWS_COGNITO_USER_POOL_ID',
                'CLIENT_ID': 'AWS_COGNITO_CLIENT_ID',
                'CLIENT_SECRET': 'AWS_COGNITO_CLIENT_SECRET',
                'IDENTITY_POOL_ID': 'AWS_COGNITO_IDENTITY_POOL_ID',
                'DOMAIN': 'AWS_COGNITO_DOMAIN',
            },
            'CAM': {
                'SECRET_ID': 'TENCENT_CAM_SECRET_ID',
                'SECRET_KEY': 'TENCENT_CAM_SECRET_KEY',
            },
        }
        for section, fields in env_map.items():
            section_cfg = config.setdefault(section, {})
            for key, env_var in fields.items():
                env_val = os.environ.get(env_var, '').strip()
                if env_val and (section_cfg.get(key) in (None, '')):
                    section_cfg[key] = env_val


class AuthConfig(metaclass=AuthConfigMeta):
    """Centralized authentication configuration with class-level access.

    Automatically loads from apps/{ECAN_APP_ID}/config/auth_config.yml.
    Usage:
        AuthConfig.CAM.SECRET_ID   # CN app
        AuthConfig.COGNITO.USER_POOL_ID  # Intl app
    """

    @classmethod
    def reload_config(cls):
        """Force reload configuration from file"""
        cls._loaded = False
        cls._loaded_app_id = None
        cls._load_config(os.environ.get('ECAN_APP_ID', 'intl'))
