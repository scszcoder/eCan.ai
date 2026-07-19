"""
Authentication Configuration
Centralized configuration management

Supports dual-app: delegates to utils.app_config_loader which loads from
apps/cn/config/auth_config.yml or apps/intl/config/auth_config.yml based on
ECAN_APP_ID env var.
"""
import os
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
            if isinstance(value, dict):
                return ConfigNamespace(value)
            return value
        raise AttributeError(f"Configuration key '{name}' not found")


def _load_legacy_auth_config(app_id: str) -> dict:
    """Fallback loader: read apps/{app_id}/config/auth_config.yml directly.

    Used as a safety net when utils.app_config_loader is unavailable
    (e.g., during early startup or in isolated test contexts).
    """
    project_root = Path(__file__).resolve().parent.parent
    app_config_path = project_root / 'apps' / app_id / 'config' / 'auth_config.yml'
    legacy_config_path = Path(__file__).parent / "auth_config.yml"

    if app_config_path.exists():
        with open(app_config_path, 'r', encoding='utf-8') as f:
            loaded = yaml.safe_load(f) or {}
        # For Intl app: merge legacy defaults when apps config has empty values.
        # The legacy auth/auth_config.yml keeps a development dev-pool as a
        # last-resort fallback so the desktop app remains usable without env vars.
        if app_id == 'intl' and legacy_config_path.exists():
            with open(legacy_config_path, 'r', encoding='utf-8') as f:
                legacy = yaml.safe_load(f) or {}
            legacy_cognito = legacy.get('COGNITO', {})
            intl_cognito = loaded.get('COGNITO', {})
            for key, val in legacy_cognito.items():
                if intl_cognito.get(key) in (None, ''):
                    intl_cognito[key] = val
            loaded['COGNITO'] = intl_cognito
        return loaded

    if legacy_config_path.exists():
        with open(legacy_config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}

    return {}


def _merge_intl_legacy_fallback(loaded: dict, app_id: str) -> dict:
    """If the app-level config has empty COGNITO fields, fall back to the
    legacy auth/auth_config.yml dev-pool values. Keeps Intl dev usable
    without requiring AWS_COGNITO_* env vars to be set.
    """
    if app_id != 'intl':
        return loaded
    legacy_path = Path(__file__).parent / 'auth_config.yml'
    if not legacy_path.exists():
        return loaded
    try:
        with open(legacy_path, 'r', encoding='utf-8') as f:
            legacy = yaml.safe_load(f) or {}
    except Exception:
        return loaded
    legacy_cognito = legacy.get('COGNITO', {})
    intl_cognito = loaded.get('COGNITO', {})
    if not isinstance(intl_cognito, dict):
        return loaded
    for key, val in legacy_cognito.items():
        if intl_cognito.get(key) in (None, '') and val not in (None, ''):
            intl_cognito[key] = val
    loaded['COGNITO'] = intl_cognito
    return loaded


def _apply_env_overrides(config: dict) -> None:
    """Override empty string values with environment variables.

    Covers all auth-related sections used by both CN and Intl apps:
    - COGNITO / CAM / WECHAT / SMS / EMAIL / GOOGLE / APPLE
    """
    env_map = {
        'COGNITO': {
            'USER_POOL_ID': 'AWS_COGNITO_USER_POOL_ID',
            'CLIENT_ID': 'AWS_COGNITO_CLIENT_ID',
            'CLIENT_SECRET': 'AWS_COGNITO_CLIENT_SECRET',
            'IDENTITY_POOL_ID': 'AWS_COGNITO_IDENTITY_POOL_ID',
            'DOMAIN': 'AWS_COGNITO_DOMAIN',
            'REGION': 'AWS_REGION',
        },
        'CAM': {
            'SECRET_ID': 'ECAN_TENCENT_SECRET_ID',
            'SECRET_KEY': 'ECAN_TENCENT_SECRET_KEY',
            'APP_ID': 'ECAN_TENCENT_APP_ID',
            'REGION': 'ECAN_TENCENT_REGION',
        },
        'WECHAT': {
            'APP_ID': 'ECAN_WECHAT_APP_ID',
            'APP_SECRET': 'ECAN_WECHAT_APP_SECRET',
        },
        'SMS': {
            'sdk_app_id': 'ECAN_TENCENT_SMS_SDK_APP_ID',
        },
        'GOOGLE': {
            'CALLBACK_URL': 'ECAN_GOOGLE_CALLBACK_URL',
        },
        'APPLE': {
            'CLIENT_ID': 'ECAN_APPLE_CLIENT_ID',
            'TEAM_ID': 'ECAN_APPLE_TEAM_ID',
            'KEY_ID': 'ECAN_APPLE_KEY_ID',
            'PRIVATE_KEY_PATH': 'ECAN_APPLE_PRIVATE_KEY_PATH',
        },
    }
    for section, fields in env_map.items():
        section_cfg = config.setdefault(section, {})
        for key, env_var in fields.items():
            env_val = os.environ.get(env_var, '').strip()
            if env_val and (section_cfg.get(key) in (None, '')):
                section_cfg[key] = env_val


class AuthConfigMeta(type):
    """Metaclass for AuthConfig to enable class-level attribute access.

    Delegates config loading to utils.app_config_loader when available,
    falling back to a local loader for early-startup isolation contexts.
    """
    _config: dict = {}
    _loaded = False
    _loaded_app_id: str | None = None

    def __getattr__(cls, name: str) -> Any:
        current_app_id = os.environ.get('ECAN_APP_ID', 'intl')
        if not cls._loaded or cls._loaded_app_id != current_app_id:
            cls._load_config(current_app_id)

        if name in cls._config:
            if isinstance(cls._config[name], dict):
                return ConfigNamespace(cls._config[name])
            return cls._config[name]
        raise AttributeError(f"Configuration section '{name}' not found")

    def _load_config(cls, app_id: str):
        """Load auth config, preferring utils.app_config_loader.

        Uses AppConfigLoader(app_id) explicitly so each app_id gets its own
        cached loader instance — supports runtime app_id switching (tests,
        dev tooling) without depending on the get_config() singleton which
        freezes the app_id at first call.
        """
        loaded: dict = {}
        try:
            from utils.app_config_loader import AppConfigLoader
            config_loader = AppConfigLoader(app_id)
            loaded = config_loader.get_auth_config() or {}
            # Intl: when the per-app config leaves COGNITO fields empty
            # (relying on env vars that may not be set), fall back to the
            # legacy dev-pool so the desktop app stays usable out of the box.
            loaded = _merge_intl_legacy_fallback(loaded, app_id)
        except Exception:
            loaded = _load_legacy_auth_config(app_id)

        _apply_env_overrides(loaded)

        cls._config = loaded
        cls._loaded = True
        cls._loaded_app_id = app_id


class AuthConfig(metaclass=AuthConfigMeta):
    """Centralized authentication configuration with class-level access.

    Delegates to utils.app_config_loader. Usage:
        AuthConfig.CAM.SECRET_ID   # CN app
        AuthConfig.COGNITO.USER_POOL_ID  # Intl app
    """

    @classmethod
    def reload_config(cls):
        """Force reload configuration (e.g., after ECAN_APP_ID change in tests)"""
        cls._loaded = False
        cls._loaded_app_id = None
        cls._load_config(os.environ.get('ECAN_APP_ID', 'intl'))
