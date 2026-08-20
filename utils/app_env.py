"""
app_env.py — 全工程统一的 CN/Intl 环境判断和基础信息获取

设计原则:
  - 所有 CN/Intl 判断和 app 信息获取通过本模块
  - 单一 `os.getenv('ECAN_APP_ID')` 读取点(在本模块)
  - 对外暴露 `app_id`, `is_cn`, `is_intl`, `auth_config` 等常用属性
  - 与 AppConfigLoader 互补: app_env 侧重运行时判断,AppConfigLoader 侧重构建时配置

使用方式:
  # 基础判断
  from utils.app_env import is_cn, is_intl, app_id

  # AuthConfig(CN:CloudBase / Intl:Cognito)
  from utils.app_env import auth
  auth.cloudbase_env_id    # CN: TCB env_id
  auth.cognito_domain      # Intl: Cognito domain
  auth.graphql_endpoint   # 统一 GraphQL URL

  # 单例
  from utils.app_env import env
  env.is_cn                # bool
  env.auth_config          # dict
  env.cloud_endpoints      # CloudEndpointConfig 实例
"""

from __future__ import annotations

import os
import threading
from typing import Any, Optional

# Lazy import for AppConfigLoader to avoid circular imports
_AppConfigLoader = None
_AuthConfig = None


# =============================================================================
# Environment variable key
# =============================================================================

ENV_KEY_APP_ID = "ECAN_APP_ID"
DEFAULT_APP_ID = "intl"


# =============================================================================
# Thread-safe lazy singletons
# =============================================================================

_local = threading.local()


def _get_app_config_loader():
    """Lazy import of AppConfigLoader (avoids circular import)."""
    global _AppConfigLoader
    if _AppConfigLoader is None:
        from utils.app_config_loader import AppConfigLoader
        _AppConfigLoader = AppConfigLoader
    return _AppConfigLoader


def _get_auth_config():
    """Lazy import of AuthConfig (avoids circular import)."""
    global _AuthConfig
    if _AuthConfig is None:
        from auth.auth_config import AuthConfig
        _AuthConfig = AuthConfig
    return _AuthConfig


# =============================================================================
# Basic accessors (no I/O)
# =============================================================================

def get_app_id() -> str:
    """Get the current ECAN_APP_ID from environment.

    Returns:
        "cn" or "intl" (never empty string, always defaults to "intl").
    """
    return os.environ.get(ENV_KEY_APP_ID, DEFAULT_APP_ID)


def is_cn() -> bool:
    """True if running the CN build."""
    return get_app_id() == 'cn'


def is_intl() -> bool:
    """True if running the Intl build."""
    return get_app_id() == 'intl'


def is_debug_build() -> bool:
    """True if ECAN_DEBUG=1 is set."""
    return os.environ.get('ECAN_DEBUG', '0') == '1'


# =============================================================================
# AuthConfig proxy (lazy, cached per-app)
# =============================================================================

def get_auth_config() -> Any:
    """Get the AuthConfig singleton for the current app.

    CN: provides COGNITO(空)/CLOUDBASE/WECHAT/SMS/EMAIL/FEATURES 等
    Intl: 提供 COGNITO/GOOGLE/APPLE/SMS/EMAIL 等

    Note: 只读访问。修改通过环境变量或重新构建 auth_config.yml。
    """
    return _get_auth_config()


def auth_cloudbase_env_id() -> str:
    """CN: Get CloudBase ENV_ID from auth_config.yml."""
    try:
        ac = _get_auth_config()
        return getattr(ac.CLOUDBASE, 'ENV_ID', '') or ''
    except AttributeError:
        return ''


def auth_cloudbase_region() -> str:
    """CN: Get CloudBase region from auth_config.yml."""
    try:
        ac = _get_auth_config()
        return getattr(ac.CLOUDBASE, 'REGION', '') or 'ap-shanghai'
    except AttributeError:
        return 'ap-shanghai'


def auth_cognito_region() -> str:
    """Intl: Get Cognito region from auth_config.yml."""
    try:
        ac = _get_auth_config()
        return getattr(ac.COGNITO, 'REGION', '') or 'us-east-1'
    except AttributeError:
        return 'us-east-1'


def auth_cognito_domain() -> str:
    """Intl: Get Cognito domain from auth_config.yml."""
    try:
        ac = _get_auth_config()
        return getattr(ac.COGNITO, 'DOMAIN', '') or ''
    except AttributeError:
        return ''


def auth_sms_provider() -> str:
    """Get SMS provider name."""
    try:
        ac = _get_auth_config()
        return getattr(ac.SMS, 'provider', '') or ''
    except AttributeError:
        return ''


# =============================================================================
# Cloud endpoints (from CloudEndpointConfig)
# =============================================================================

def get_cloud_endpoint_config():
    """Get CloudEndpointConfig singleton (unified CN/Intl endpoints)."""
    from agent.cloud_api.endpoints import get_endpoint_config as _get_ep
    return _get_ep()


# =============================================================================
# AppConfigLoader proxy
# =============================================================================

def get_app_config() -> Any:
    """Get AppConfigLoader for the current app (lazy, cached).

    Use this for build-time / manifest config:
      - app_name, app_short_name
      - bundle_id, url_scheme
      - storage_url (from cloud_endpoints.json -> 'storage')
      - cloud_graphql_endpoint / cloud_ws_endpoint (from auth_config.yml -> APPSYNC.*)
    """
    return _get_app_config_loader()()


# =============================================================================
# Payment config (from apps/{app_id}/config/payment_config.json)
# =============================================================================

def get_payment_config() -> dict:
    """Load apps/{app_id}/config/payment_config.json for the current app.

    Public fields only (entry_url / status_url_base / methods). Merchant
    secrets live server-side in the payment endpoints and are never read
    here. Returns {} if the file is absent or unreadable.
    """
    import json
    from pathlib import Path
    project_root = Path(__file__).resolve().parent.parent
    path = project_root / 'apps' / get_app_id() / 'config' / 'payment_config.json'
    try:
        if path.exists():
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {}


# =============================================================================
# Convenience flags
# =============================================================================

def is_mobile_build() -> bool:
    """True if ECAN_MOBILE=1 is set."""
    return os.environ.get('ECAN_MOBILE', '0') == '1'


def is_sandbox_build() -> bool:
    """True if ECAN_SANDBOX=1 is set."""
    return os.environ.get('ECAN_SANDBOX', '0') == '1'


def is_dev_mode() -> bool:
    """True if ECAN_DEV=1 is set."""
    return os.environ.get('ECAN_DEV', '0') == '1'


# =============================================================================
# Exported symbols (for "from utils.app_env import *")
# =============================================================================

__all__ = [
    # Env key & basic accessors
    'ENV_KEY_APP_ID', 'DEFAULT_APP_ID',
    'get_app_id', 'is_cn', 'is_intl',
    'is_debug_build', 'is_mobile_build', 'is_sandbox_build', 'is_dev_mode',
    # AuthConfig shortcuts
    'get_auth_config',
    'auth_cloudbase_env_id', 'auth_cloudbase_region',
    'auth_cognito_region', 'auth_cognito_domain',
    'auth_sms_provider',
    # Cloud endpoints
    'get_cloud_endpoint_config',
    # AppConfigLoader
    'get_app_config',
    # Payment
    'get_payment_config',
]


# =============================================================================
# Backward-compat aliases (deprecated, pointing to canonical locations)
# =============================================================================

# Legacy name that existed in multiple places — now unified here
def is_cn_app() -> bool:
    """Deprecated: use is_cn() or env.is_cn instead."""
    return is_cn()


def _is_cn_app() -> bool:
    """Deprecated: use is_cn() or env.is_cn instead."""
    return is_cn()
