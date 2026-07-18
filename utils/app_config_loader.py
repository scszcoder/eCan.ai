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


PROJECT_ROOT: Path = getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent)


def _get_project_root() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(getattr(sys, '_MEIPASS'))
    return Path(__file__).resolve().parent.parent


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
            raise FileNotFoundError(f"Config file not found: {path}")
        with open(path, encoding='utf-8') as f:
            return json.load(f)

    def _load_manifest(self) -> dict:
        return self._load_json(self._config_dir / 'app_manifest.json')

    def _load_endpoints(self) -> dict:
        return self._load_json(self._config_dir / 'cloud_endpoints.json')

    def _load_auth_config(self) -> dict:
        auth_file = self._config_dir / 'auth_config.yml'
        if not auth_file.exists():
            return {}
        if yaml is None:
            raise ImportError("PyYAML is required to load auth_config.yml. Install with: pip install pyyaml")
        with open(auth_file, encoding='utf-8') as f:
            return yaml.safe_load(f) or {}

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
    def graphql_url(self) -> str:
        return self.get_endpoint('graphql')

    @property
    def websocket_url(self) -> str:
        return self.get_endpoint('websocket')

    @property
    def auth_url(self) -> str:
        return self.get_endpoint('auth')

    @property
    def storage_url(self) -> str:
        return self.get_endpoint('storage')

    @property
    def update_url(self) -> str:
        return self.get_endpoint('update')

    @property
    def privacy_policy_url(self) -> str:
        return self.get_endpoint('privacy_policy')

    @property
    def terms_url(self) -> str:
        return self.get_endpoint('terms_of_service')

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


# --- Global shortcut ---
_app_config: Optional[AppConfigLoader] = None


def get_config() -> AppConfigLoader:
    """获取当前 app 配置（全局单例）"""
    global _app_config
    if _app_config is None:
        _app_config = AppConfigLoader()
    return _app_config
