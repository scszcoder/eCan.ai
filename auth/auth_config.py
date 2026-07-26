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


class _MissingAttr:
    """Sentinel returned when a per-app config doesn't declare a key.

    Behaves like None for falsy checks and string ops, but `hasattr(ns, k)`
    returns False for it (because we set it on the instance dict, not via
    __getattr__). This preserves the ability to distinguish "this auth
    scheme isn't available on this app" from "the value is empty string".
    """

    def __bool__(self):
        return False

    def __repr__(self):
        return '<MISSING>'


_MISSING = _MissingAttr()


class ConfigNamespace:
    """Dynamic namespace for accessing config sections.

    Per-app auth_config.yml only contains sections relevant to that app
    (Intl has COGNITO/GOOGLE/APPLE; CN has CLOUDBASE/WECHAT). When code accesses
    a section that doesn't apply to the current app — e.g.
    `AuthConfig.CLOUDBASE.ENV_ID` on Intl — we return a falsy sentinel
    (``None``-ish) so the call doesn't crash.

    To distinguish "missing" from "explicit empty string", use:
      * `hasattr(ns, key)` — returns False only for missing keys
      * `getattr(ns, key, default)` — default only on missing keys
      * `ns._config.get(key) is _MISSING` — explicit check
    """

    def __init__(self, config_dict: dict):
        self._config = config_dict

    def __getattr__(self, name: str) -> Any:
        # Internal lookup of our own attributes — always allow normal attribute
        # access so the namespace itself keeps working.
        if name == '_config':
            raise AttributeError(name)
        if name in self._config:
            value = self._config[name]
            if isinstance(value, dict):
                return ConfigNamespace(value)
            return value
        # Per-app configs only declare sections they use; missing keys mean
        # "this auth scheme isn't available on this app", not a programming error.
        # Cache the sentinel in self.__dict__ so hasattr() returns True (the
        # key IS addressable, just falsy) — callers that need to distinguish
        # "missing" from "empty" can use ns._config.get(key, _MISSING) is _MISSING
        # or check `if ns._config.get(key) is _MISSING`.
        self.__dict__[name] = _MISSING
        return _MISSING

    def __contains__(self, key: str) -> bool:
        """`key in ns` — distinguishes missing from empty."""
        return key in self._config

    def get(self, key: str, default: Any = None) -> Any:
        """ns.get(key, default) — only returns default when key is truly missing."""
        if key in self._config:
            return self._config[key]
        return default


_LOAD_CONFIG_FILE = 'auth_config.yml'
_LEGACY_CONFIG_FILE = 'auth_config.yml'

# 严禁出现在 yml 仓库文件里的字段（只能从 env 注入）
_FORBIDDEN_YML_KEYS: tuple = (
    # 腾讯云
    'SECRET_ID', 'SECRET_KEY',
    # 微信
    'APP_SECRET',
    # JWT
    'SECRET', 'JWT_SECRET',
    # Apple 私钥
    'PRIVATE_KEY',
)


def _reject_forbidden_keys(config: dict, source: str) -> None:
    """私密字段必须仅来自环境变量，不能写在 yml 里。

    yml 会随 App 打包（参见 apps/cn/config/auth_config.yml 文档），
    如果有人把 SECRET_KEY 写进 yml，构建产物会泄露。明令禁止并 fail-fast。
    """
    for section, fields in config.items():
        if not isinstance(fields, dict):
            continue
        for key in fields:
            if key.upper() in _FORBIDDEN_YML_KEYS:
                raise RuntimeError(
                    f"[{source}] 私密字段 '{section}.{key}' 不允许出现在 yml 文件中，"
                    f"必须仅通过环境变量注入。"
                )


def _load_legacy_auth_config(app_id: str) -> dict:
    """Fallback loader used only when utils.app_config_loader is unavailable
    (early startup or isolated test contexts).

    Reads apps/{app_id}/config/auth_config.yml first; falls back to the
    shared auth/auth_config.yml file when the per-app one is absent.

    Note: the Intl legacy-merge step previously embedded here (lines 95-107)
    is intentionally removed — that path is only reached after
    AppConfigLoader already failed, so re-merging is duplicate work. The
    happy path uses _merge_intl_legacy_fallback() after AppConfigLoader
    succeeds.
    """
    project_root = Path(__file__).resolve().parent.parent
    app_config_path = project_root / 'apps' / app_id / 'config' / 'auth_config.yml'
    if app_config_path.exists():
        with open(app_config_path, 'r', encoding='utf-8') as f:
            loaded = yaml.safe_load(f) or {}
        _reject_forbidden_keys(loaded, f"apps/{app_id}/config/auth_config.yml")
        return loaded

    legacy_config_path = Path(__file__).parent / "auth_config.yml"
    if legacy_config_path.exists():
        with open(legacy_config_path, 'r', encoding='utf-8') as f:
            loaded = yaml.safe_load(f) or {}
        _reject_forbidden_keys(loaded, "auth/auth_config.yml")
        return loaded

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
    - COGNITO / CLOUDBASE / WECHAT / SMS / EMAIL / GOOGLE / APPLE
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
        'CLOUDBASE': {
            'ENV_ID': 'ECAN_TENCENT_CLOUDBASE_ENV_ID',
            'SECRET_ID': 'ECAN_TENCENT_SECRET_ID',
            'SECRET_KEY': 'ECAN_TENCENT_SECRET_KEY',
            'REGION': 'ECAN_TENCENT_REGION',
        },
        'WECHAT': {
            'APP_ID': 'ECAN_WECHAT_APP_ID',
            'APP_SECRET': 'ECAN_WECHAT_APP_SECRET',
        },
        'SMS': {
            'sdk_app_id': 'ECAN_TENCENT_SMS_SDK_APP_ID',
        },
        'JWT': {
            'secret': 'ECAN_JWT_SECRET',
            'expires_in': 'ECAN_JWT_EXPIRES_IN',
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
            _reject_forbidden_keys(loaded, "AppConfigLoader")
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
        AuthConfig.CLOUDBASE.ENV_ID   # CN app
        AuthConfig.COGNITO.USER_POOL_ID  # Intl app
    """

    @classmethod
    def reload_config(cls):
        """Force reload configuration (e.g., after ECAN_APP_ID change in tests)"""
        cls._loaded = False
        cls._loaded_app_id = None
        cls._load_config(os.environ.get('ECAN_APP_ID', 'intl'))
