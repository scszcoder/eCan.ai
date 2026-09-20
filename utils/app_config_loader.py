"""
App Config Loader - 统一配置加载器
根据 ECAN_APP_ID 环境变量加载对应 app 的配置（cn / intl）

所有 app 差异化配置通过此模块注入，禁止在共享代码中硬编码 app 判断。
"""
import json
import os
import sys
from pathlib import Path
from functools import lru_cache
from typing import Any, Optional

try:
    import yaml
except ImportError:
    yaml = None  # 仅在需要 YAML 时要求安装


def _resolve_project_root() -> Path:
    """Resolve the project / bundle root.

    Under PyInstaller one-folder/one-file builds, ``sys._MEIPASS`` is set
    by the bootloader to the absolute path of the bundle folder — but as a
    ``str``, not a ``pathlib.Path``. The previous module-level expression
    ``getattr(sys, '_MEIPASS', Path(...))`` returned that string verbatim,
    which then blew up the first time callers did
    ``PROJECT_ROOT / 'apps' / 'cn'`` (a string divided by a string raises
    ``TypeError: unsupported operand type(s) for /: 'str' and 'str'``).
    That exception was swallowed inside
    ``ota.core.installer._get_current_windows_install_dir`` and caused the
    OTA upgrade to silently fall back to the wrong install directory —
    Inno Setup then wrote the new version to a side directory while the
    running exe stayed on the old version.

    Always coerce to ``Path`` so ``PROJECT_ROOT / 'x'`` is well-typed in
    every runtime mode (frozen, dev, CI test).
    """
    if getattr(sys, 'frozen', False):
        meipass = getattr(sys, '_MEIPASS', None)
        if meipass:
            return Path(meipass)
    return Path(__file__).resolve().parent.parent


PROJECT_ROOT: Path = _resolve_project_root()


def _get_project_root() -> Path:
    # Kept as a public helper for callers that want a function reference
    # rather than the module-level constant. Delegates to the same
    # resolver so the two cannot drift.
    return _resolve_project_root()


class AppConfigLoader:
    """
    统一配置加载器。

    优先级：
    1. ECAN_APP_ID 环境变量（打包时注入）
    2. 默认为 intl（国际版）

    使用示例：
        config = AppConfigLoader()
        config.get('graphql')         # → endpoint URL
        config.get_auth_config()      # → auth dict
        config.is_cn()                # → bool
    """

    _instances: dict[str, 'AppConfigLoader'] = {}

    def __new__(cls, app_id: Optional[str] = None) -> 'AppConfigLoader':
        if app_id is None:
            app_id = os.environ.get('ECAN_APP_ID', 'intl')
        if app_id not in cls._instances:
            instance = super().__new__(cls)
            cls._instances[app_id] = instance
        return cls._instances[app_id]

    def __init__(self, app_id: Optional[str] = None):
        if hasattr(self, '_initialized'):
            return
        self.app_id: str = app_id or os.environ.get('ECAN_APP_ID', 'intl')
        self._project_root: Path = _get_project_root()
        self._app_dir: Path = self._project_root / 'apps' / self.app_id
        self._config_dir: Path = self._app_dir / 'config'
        self._manifest: dict = self._load_manifest()
        self._endpoints: dict = self._load_endpoints()
        self._auth_config: dict = self._load_auth_config()
        self._initialized = True

    def _load_json(self, path: Path) -> dict:
        if not path.exists():
            return {}
        try:
            with open(path, encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            # Per-file load failures are non-fatal: callers see an empty dict
            # and fall back to whatever defaults the manifest accessors provide.
            # This lets build code stop wrapping AppConfigLoader() in try/except
            # just to handle a missing optional config file.
            return {}

    def _load_manifest(self) -> dict:
        return self._load_json(self._config_dir / 'app_manifest.json')

    def _load_endpoints(self) -> dict:
        return self._load_json(self._config_dir / 'cloud_endpoints.json')

    def _load_auth_config(self) -> dict:
        auth_file = self._config_dir / 'auth_config.yml'
        if not auth_file.exists() or yaml is None:
            return {}
        try:
            with open(auth_file, encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except Exception:
            return {}

    # --- App Identity ---
    def is_cn(self) -> bool:
        return self.app_id == 'cn'

    def is_intl(self) -> bool:
        return self.app_id == 'intl'

    # --- Manifest Accessors ---
    def get(self, key: str, default: Any = None) -> Any:
        return self._manifest.get(key, default)

    @property
    def app_name(self) -> str:
        return self._manifest.get('app_name', 'eCan')

    @property
    def app_short_name(self) -> str:
        return self._manifest.get('app_short_name', 'eCan')

    @property
    def bundle_id(self) -> str:
        import platform
        p = platform.system().lower()
        if p == 'darwin':
            return self._manifest.get('bundle_id', {}).get('macos', 'com.ecan.app')
        elif p == 'windows':
            return self._manifest.get('bundle_id', {}).get('windows', 'com.ecan.app')
        else:
            return self._manifest.get('bundle_id', {}).get('linux', 'com.ecan.app')

    @property
    def url_scheme(self) -> str:
        return self._manifest.get('url_scheme', 'ecan://')

    @property
    def primary_language(self) -> str:
        return self._manifest.get('primary_language', 'en')

    @property
    def default_currency(self) -> str:
        return self._manifest.get('default_currency', 'USD')

    @property
    def default_timezone(self) -> str:
        return self._manifest.get('default_timezone', 'America/Los_Angeles')

    @property
    def cloud_provider(self) -> str:
        return self._manifest.get('cloud_provider', 'aws')

    # --- Endpoint Accessors ---
    def get_endpoint(self, name: str) -> str:
        return self._endpoints.get(name, '')

    @property
    def storage_url(self) -> str:
        return self.get_endpoint('storage')

    # --- CloudEndpoints (统一端点,来自 auth_config.yml APPSYNC.*) ---
    @property
    def cloud_graphql_endpoint(self) -> str:
        """Cloud GraphQL HTTP 端点(CN:TCB / Intl:AppSync)。

        生产代码的真值源 — 由 agent/cloud_api/endpoints.py 通过
        auth.auth_config.AuthConfig.APPSYNC.* 读取。本属性仅作为
        AppConfigLoader 上的统一访问层，未来代码可使用。
        """
        return self._auth_config.get('APPSYNC', {}).get('GRAPHQL_ENDPOINT', '')

    @property
    def cloud_ws_endpoint(self) -> str:
        """Cloud WebSocket 端点(CN:TCB / Intl:AppSync realtime)。"""
        return self._auth_config.get('APPSYNC', {}).get('WS_ENDPOINT', '')

    @property
    def cloud_api_key(self) -> str:
        """Cloud API Key (可能为空字符串)。"""
        return self._auth_config.get('APPSYNC', {}).get('API_KEY', '')

    @property
    def cloud_region(self) -> str:
        """Cloud 区域(CN:ap-shanghai / Intl:us-east-1)。"""
        return self._auth_config.get('APPSYNC', {}).get('REGION', '')

    @property
    def cloud_ws_host(self) -> str:
        """Cloud WebSocket Host(从 WS_ENDPOINT 解析)。"""
        from urllib.parse import urlparse
        ws = self.cloud_ws_endpoint
        if not ws:
            return ''
        return urlparse(ws).netloc

    # --- Auth Config ---
    def get_auth_config(self) -> dict:
        return self._auth_config

    def get_auth_provider(self) -> str:
        config = self._auth_config
        if 'CAM' in config or 'WECHAT' in config:
            return 'tencent'
        if 'COGNITO' in config:
            return 'aws_cognito'
        return 'unknown'

    def get(self, key: str, default: Any = None) -> Any:
        return self._manifest.get(key, default)

    def get_storage_config(self) -> dict:
        return {
            'provider': self.cloud_provider,
            'region': self._endpoints.get('storage_region', ''),
            'bucket': self._endpoints.get('storage_bucket', ''),
            'endpoint': self.storage_url,
        }


@lru_cache(maxsize=2)
def get_app_config(app_id: Optional[str] = None) -> AppConfigLoader:
    """全局配置实例获取（带缓存）"""
    return AppConfigLoader(app_id)


# ``AppConfigLoader._instances`` is a module-level singleton keyed by
# ``app_id``. The ``@lru_cache`` above is a second cache on the same
# objects. Clearing only one leaves stale data — the singleton for
# callers that go through ``AppConfigLoader(...)`` directly, the
# ``lru_cache`` for callers that go through ``get_app_config(...)``.
# Patch ``cache_clear`` so test fixtures (and any future runtime
# invalidation) clear both.
_orig_cache_clear = get_app_config.cache_clear


def _clear_app_config_caches():
    """Clear both the ``lru_cache`` and the ``_instances`` singleton.

    Use this instead of calling ``get_app_config.cache_clear()`` directly
    when you want a fully-reset state (e.g. tests that monkeypatch
    ``_get_project_root`` or rewrite the manifest file on disk)."""
    _orig_cache_clear()
    AppConfigLoader._instances.clear()


get_app_config.cache_clear = _clear_app_config_caches  # type: ignore[assignment]


def get_config() -> AppConfigLoader:
    """Get the AppConfigLoader for the current app (no stale caching).

    Reads ECAN_APP_ID at every call so runtime app switches (tests, dev tooling,
    packaged binaries that re-exec with a different app id) always pick up the
    current value instead of returning the first-ever instantiation.
    """
    return get_app_config(os.environ.get('ECAN_APP_ID', 'intl'))


# ----------------------------------------------------------------------------
# Build-config helpers
# ----------------------------------------------------------------------------
# Single source of truth for which build_config_{app_id}.json to read and what
# the Windows AppId GUID for Inno Setup / OTA uninstall should be. Before these
# helpers, three modules (ecan_build, url_scheme_config, ota/core/installer)
# each reimplemented this with slight variations.

DEFAULT_INTL_GUID = '6E1CCB74-1C0D-4333-9F20-2E4F2AF3F4A1'

# CN's default GUID, in mirror of the intl one. Used as the fallback when
# ``apps/cn/build/build_config_cn.json`` is missing or malformed — without
# this, ``get_windows_app_id('cn')`` would silently return the INTL GUID,
# and the OTA registry lookup would query the wrong uninstall key on a
# CN user's machine. CN builds actually registered with Inno Setup use
# this same GUID (mirrored from apps/cn/build/build_config_cn.json
# :installer.windows.app_id), so it produces a well-formed registry
# query instead of a silent miss-then-fall-back to the intl key.
DEFAULT_CN_GUID = '8E2A1B3C-4D5E-6F7A-8B9C-0D1E2F3A4B5C'

# CN's default app short name (mirrors DEFAULT_CN_GUID). Used by
# ``ota.core.installer._resolve_app_short_name`` when the per-app
# manifest is missing or unreadable so a CN machine does not silently
# install into the intl-style dir (``%LOCALAPPDATA%\\eCan``,
# ``~/.local/bin/eCan.AppImage``, ``/usr/bin/ecan``, etc.). Matches
# the value in apps/cn/config/app_manifest.json:app_short_name.
DEFAULT_CN_APP_SHORT_NAME = 'eCan.cn'
# Inttl's default short name. ``eCan`` (no suffix) — mirrors what the
# intl manifest ships with.
DEFAULT_INTL_APP_SHORT_NAME = 'eCan'


def get_build_config_path(app_id: Optional[str] = None) -> Path:
    """Path to apps/{app_id}/build/build_config_{app_id}.json.

    Falls back to build_system/build_config.json when the per-app file is
    missing or app_id is something other than 'cn' / 'intl'. Replaces the
    duplicate copies that previously lived in unified_build.py and
    url_scheme_config.py.
    """
    effective = app_id or os.environ.get('ECAN_APP_ID', 'intl')
    if effective not in ('cn', 'intl'):
        return PROJECT_ROOT / 'build_system' / 'build_config.json'
    per_app = PROJECT_ROOT / 'apps' / effective / 'build' / f'build_config_{effective}.json'
    if per_app.exists():
        return per_app
    return PROJECT_ROOT / 'build_system' / 'build_config.json'


def _default_guid_for_app_id(app_id: Optional[str]) -> str:
    """Return the per-app default GUID used when build_config is missing.

    Returns ``DEFAULT_CN_GUID`` when CN is requested, ``DEFAULT_INTL_GUID``
    otherwise. The two defaults are distinct so a CN lookup never
    silently degrades into an intl-key query — the symptom would be
    "registry key not found, falling back to default install dir" on
    every CN user's machine, which is exactly the silent-fallback
    failure this helper exists to prevent.
    """
    if (app_id or os.environ.get('ECAN_APP_ID', 'intl')) == 'cn':
        return DEFAULT_CN_GUID
    return DEFAULT_INTL_GUID


def get_windows_app_id(app_id: Optional[str] = None) -> str:
    """Resolve the Windows AppId GUID for Inno Setup and OTA uninstall lookup.

    Reads apps/{app_id}/build/build_config_{app_id}.json:installer.windows.app_id
    (falling back to installer.app_id). Braces and surrounding whitespace are
    stripped so callers get a clean hex string.

    The fallback uses the per-app default GUID (``DEFAULT_CN_GUID`` for
    ``cn``, ``DEFAULT_INTL_GUID`` for everything else) rather than a
    single shared value, so a missing CN config does NOT silently
    degrade the registry lookup into an intl-key query. Both defaults
    are well-formed GUIDs matching what the corresponding per-app Inno
    Setup build registers, so the registry query still targets the
    correct uninstall entry. A WARNING is logged when we fall back so
    the operator notices if the build_config file disappears in
    production.

    Implementation note: ``get_build_config_path`` itself falls back
    to ``build_system/build_config.json`` (which carries the INTL
    GUID) when the per-app file is missing. We MUST NOT use that
    fallback path as the "configured" value — reading the INTL GUID
    out of the system file would silently regress CN users to the
    intl registry key, which is exactly the bug this helper exists
    to prevent. Instead we re-derive the per-app path here and use
    the per-app default when that file is missing or malformed.
    """
    requested = app_id or os.environ.get('ECAN_APP_ID', 'intl')
    default_guid = _default_guid_for_app_id(requested)

    # Compute the per-app file path directly (do NOT use
    # ``get_build_config_path`` — it falls back to the system config
    # and would silently return the INTL GUID for a missing CN file).
    if requested in ('cn', 'intl'):
        per_app_cfg = PROJECT_ROOT / 'apps' / requested / 'build' / f'build_config_{requested}.json'
    else:
        per_app_cfg = None

    raw: Any = default_guid
    used_default = True
    if per_app_cfg is not None and per_app_cfg.exists():
        try:
            with open(per_app_cfg, encoding='utf-8') as f:
                cfg = json.load(f)
            installer_cfg = cfg.get('installer', {}) if isinstance(cfg, dict) else {}
            configured = (installer_cfg.get('windows', {}) or {}).get('app_id') \
                or installer_cfg.get('app_id')
            if configured:
                raw = configured
                used_default = False
        except Exception:
            # Malformed build_config — fall through to default + warn.
            raw = default_guid

    if used_default:
        # Lazy logger import to avoid a hard dependency on the
        # logger_helper module from this config-loading helper.
        try:
            from utils.logger_helper import logger_helper
            if per_app_cfg is None:
                # ``requested`` is not 'cn' or 'intl' — there is no
                # per-app build_config path at all. Different root cause
                # than "file missing", so log a distinct message that
                # doesn't reference a non-existent path.
                logger_helper.warning(
                    "[AppConfig] Falling back to default Windows AppId "
                    "for unknown app_id=%r (only 'cn' / 'intl' have a "
                    "per-app build_config; got requested=%r). Registry "
                    "lookup will use the intl default GUID. Verify the "
                    "caller is passing a valid app_id.",
                    requested, requested,
                )
            else:
                logger_helper.warning(
                    "[AppConfig] Falling back to default Windows AppId "
                    "for app_id=%r (per-app build_config missing or has no "
                    "installer.windows.app_id; expected at %s). Registry "
                    "lookup will use the per-app default GUID; verify "
                    "build_config is deployed alongside the binary.",
                    requested, per_app_cfg,
                )
        except Exception:
            pass

    return str(raw).strip().strip('{}').strip() or default_guid
