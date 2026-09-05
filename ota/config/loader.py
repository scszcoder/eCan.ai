"""
Simple OTA Configuration Loader
Loads configuration from ota_config.yaml

Supports CN/INTL separation:
  - CN app (ECAN_APP_ID=cn): Uses Tencent Cloud COS storage
  - INTL app (ECAN_APP_ID=intl): Uses AWS S3 storage
"""

import os
import yaml
from pathlib import Path
from typing import Any, Optional, Dict
from utils.logger_helper import logger_helper as logger
from utils.app_env import get_app_id, is_cn as _is_cn_func


class OTAConfig:
    """Simple OTA configuration loader with CN/INTL support"""
    
    def __init__(self, config_file: Optional[str] = None):
        """
        Initialize OTA configuration
        
        Args:
            config_file: Path to configuration file (default: ota_config.yaml)
        """
        if config_file is None:
            # Try to find config file in project root
            config_file = self._find_config_file()
        
        self._config = self._load_config(config_file)
        self._validate_config()
        
        # Detect CN/INTL app type from environment
        self._app_id = get_app_id()
        self._is_cn = _is_cn_func()
        
        if self.enabled:
            storage_backend = "COS (CN)" if self._is_cn else "S3 (INTL)"
            logger.info(f"[OTA Config] Loaded configuration from {config_file}")
            logger.info(f"[OTA Config] App Type: {self._app_id} ({storage_backend})")
            logger.info(f"[OTA Config] Environment: {self.environment}")
            logger.info(f"[OTA Config] Storage Backend: {storage_backend}")
        else:
            logger.info("[OTA Config] OTA is disabled")
    
    def _find_config_file(self) -> str:
        """Find configuration file in ota/config directory"""
        # First try ota/config/ota_config.yaml relative to current file
        current_file = Path(__file__).parent
        config_path = current_file / "ota_config.yaml"
        if config_path.exists():
            return str(config_path)
        
        # Try project root
        current = Path.cwd()
        for _ in range(5):  # Search up to 5 levels
            # Try ota/config/ota_config.yaml
            config_path = current / "ota" / "config" / "ota_config.yaml"
            if config_path.exists():
                return str(config_path)
            current = current.parent
        
        # Default path
        return "ota/config/ota_config.yaml"
    
    def _load_config(self, config_file: str) -> Dict:
        """Load configuration from YAML file"""
        config_path = Path(config_file)
        
        if not config_path.exists():
            logger.warning(f"[OTA Config] Configuration file not found: {config_file}")
            logger.warning("[OTA Config] OTA will be disabled")
            return {'ota_enabled': False, 'environment': 'production'}
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            return config or {}
        except Exception as e:
            logger.error(f"[OTA Config] Failed to load configuration: {e}")
            return {'ota_enabled': False, 'environment': 'production'}
    
    def _validate_config(self):
        """Validate configuration"""
        if not self.enabled:
            return
        
        # Check required fields
        if 'environment' not in self._config:
            logger.error("[OTA Config] Missing 'environment' in configuration")
            self._config['ota_enabled'] = False
            return
        
        env = self.environment
        if 'environments' not in self._config or env not in self._config['environments']:
            logger.error(f"[OTA Config] Environment '{env}' not found in configuration")
            self._config['ota_enabled'] = False
            return
        
        logger.info("[OTA Config] Configuration validation passed")
    
    @property
    def enabled(self) -> bool:
        """Check if OTA is enabled"""
        return self._config.get('ota_enabled', False)
    
    @property
    def environment(self) -> str:
        """Get current environment"""
        return self._config.get('environment', 'production')
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value for current environment
        
        Args:
            key: Configuration key
            default: Default value if key not found
            
        Returns:
            Configuration value
        """
        if not self.enabled:
            return default
        
        env = self.environment
        env_config = self._config.get('environments', {}).get(env, {})
        return env_config.get(key, default)
    
    def get_common(self, key: str, default: Any = None) -> Any:
        """
        Get common configuration value
        
        Args:
            key: Configuration key
            default: Default value if key not found
            
        Returns:
            Configuration value
        """
        return self._config.get('common', {}).get(key, default)
    
    def get_advanced(self, key: str, default: Any = None) -> Any:
        """
        Get advanced configuration value
        
        Args:
            key: Configuration key
            default: Default value if key not found
            
        Returns:
            Configuration value
        """
        return self._config.get('advanced', {}).get(key, default)
    
    def get_app_name(self) -> str:
        """Return application display name from common config (e.g. 'eCan')."""
        return str(self.get_common('app_name', 'eCan'))
    
    def get_latest_json_url(self) -> str:
        """
        Get latest.json URL for the current environment (with CN/INTL support).

        CN app uses Tencent Cloud COS, INTL app uses AWS S3.
        The returned path matches what
        ``build_system/scripts/generate_appcast.py::generate_latest_json``
        writes (``{prefix}/latest.json``) — same shape as
        ``get_appcast_url``'s ``channels/...`` siblings.

        Used by the "manual install" fallback link in the OTA dialogs so
        the user is sent to the correct bucket (COS vs S3) and the
        correct environment prefix (``dev``, ``test``, ``staging``,
        ``simulation``, ``production``) instead of always pointing at
        the hardcoded INTL/production S3 URL.

        Returns:
            Empty string if OTA is disabled; otherwise the full
            COS/S3 URL to ``{prefix}/latest.json``.

        Example:
            # CN app (ECAN_APP_ID=cn), test env (active)
            get_latest_json_url()
            → https://ecan-releases-1251680599.cos.ap-shanghai.myqcloud.com/test/latest.json

            # INTL app (ECAN_APP_ID=intl), test env (active)
            get_latest_json_url()
            → https://ecan-releases.s3.us-east-1.amazonaws.com/test/latest.json
        """
        if not self.enabled:
            return ""

        # Active env (default: test) declares ``appcast_base`` /
        # ``appcast_base_cos`` — the override is the canonical way to
        # reach the bucket (works for local dev server AND remote
        # test/staging/production hosts). Fall through only when no
        # override is declared at all.
        local_base = self._local_appcast_base()
        if local_base:
            return f"{local_base.rstrip('/')}/latest.json"

        return self.get_storage_url("latest.json")

    def _local_appcast_base(self) -> str:
        """
        Return the active environment's ``appcast_base`` URL when one
        is explicitly declared, else ``""``.

        Reads ``appcast_base`` (INTL) or ``appcast_base_cos`` (CN) from
        the current environment block. Any non-empty value is honored
        as an override of the public S3/COS bucket — both local
        (``http://127.0.0.1:8080``) and remote public hosts
        (``https://ecan-releases.s3.us-east-1.amazonaws.com/test``,
        etc.) qualify. staging/simulation/production/test all set this
        field to their public host and the override is the canonical
        way they reach the bucket — falling through to
        ``get_storage_url`` would silently use a different bucket
        (INTL/COS mismatch) or drop the channel segment.

        Returns:
            Base URL with trailing ``/`` stripped, or ``""`` when no
            override is declared.
        """
        env_config = self._config.get('environments', {}).get(self.environment, {}) or {}
        if self._is_cn:
            base = env_config.get('appcast_base_cos') or env_config.get('appcast_base')
        else:
            base = env_config.get('appcast_base')
        if not base:
            return ""
        return base.rstrip('/')

    def get_appcast_url(self, platform: str, arch: Optional[str] = None, language: Optional[str] = None) -> str:
        """
        Get appcast URL for platform and architecture (with CN/INTL support)

        CN app uses Tencent Cloud COS, INTL app uses AWS S3.

        Args:
            platform: Platform name (macos, windows, linux)
            arch: Architecture (aarch64, amd64), optional
            language: Language code (e.g., 'en-US', 'zh-CN'), optional

        Returns:
            Appcast URL (COS for CN app, S3 for INTL app). When the
            current environment declares ``appcast_base`` (INTL) /
            ``appcast_base_cos`` (CN) — which the canonical
            environments ``test`` / ``staging`` / ``simulation`` /
            ``production`` all do, and ``development`` does for the
            local OTA test server — the URL is built off that base as
            ``{base}/channels/{channel}/{filename}`` so the path
            matches whatever upload pipeline (``upload_to_s3.py`` /
            ``upload_to_cos.py``) wrote. The ``language`` suffix is
            always honored so per-language copies (e.g.
            ``appcast-macos-aarch64.zh-CN.xml``) are addressable
            whether the artifact lives in S3/COS or on the local
            server.

        Example:
            # CN app (ECAN_APP_ID=cn), test env (active)
            get_appcast_url('macos', 'aarch64')
            → https://ecan-releases-1251680599.cos.ap-shanghai.myqcloud.com/test/channels/beta/appcast-macos-aarch64.xml

            # INTL app (ECAN_APP_ID=intl), test env (active)
            get_appcast_url('macos', 'aarch64')
            → https://ecan-releases.s3.us-east-1.amazonaws.com/test/channels/beta/appcast-macos-aarch64.xml

            # With language support
            get_appcast_url('macos', 'aarch64', 'zh-CN')
            → https://ecan-releases-1251680599.cos.ap-shanghai.myqcloud.com/test/channels/beta/appcast-macos-aarch64.zh-CN.xml
        """
        if not self.enabled:
            return ""

        # Build appcast filename with language support
        if arch:
            base_filename = f"appcast-{platform}-{arch}"
        else:
            base_filename = f"appcast-{platform}"

        # Add language suffix if not English
        if language and language != 'en-US':
            filename = f"{base_filename}.{language}.xml"
        else:
            filename = f"{base_filename}.xml"

        # Active environment declares ``appcast_base`` → build URL off
        # that base. Path mirrors ``get_storage_url`` so a client that
        # uploads via the public pipeline reads identically whether
        # it later resolves the URL via the override or the fallback.
        local_base = self._local_appcast_base()
        if local_base:
            return f"{local_base}/channels/{self.get_channel()}/{filename}"

        # No override declared → fall through to public S3/COS storage.
        return self.get_storage_url(f"channels/{self.get_channel()}/{filename}")
    
    def get_s3_prefix(self) -> str:
        """
        Get S3 path prefix for current environment
        
        Returns:
            S3 prefix (e.g., 'dev', 'test', 'staging', 'production')
        """
        return self.get('s3_prefix', self.environment)
    
    def get_channel(self) -> str:
        """
        Get release channel for current environment
        
        Returns:
            Channel name (e.g., 'dev', 'beta', 'stable', 'lts')
        """
        return self.get('channel', 'stable')
    
    def get_cos_url(self, path: str) -> str:
        """
        Construct Tencent Cloud COS URL for a given path
        
        Args:
            path: Path relative to environment prefix (e.g., 'channels/stable/appcast-macos-amd64.xml')
            
        Returns:
            Full COS URL with base path and environment prefix
            
        Example:
            get_cos_url('channels/stable/appcast-macos-amd64.xml')
            → https://ecan-releases-1251680599.cos.ap-shanghai.myqcloud.com/production/channels/stable/appcast-macos-amd64.xml
        """
        if not self.enabled:
            return ""

        cos_bucket = self.get_common('cos_bucket', 'ecan-releases-1251680599')
        cos_region = self.get_common('cos_region', 'ap-shanghai')
        cos_prefix = self.get('cos_prefix', self.environment)

        # Combine: bucket + region + prefix + path
        # Example: ecan-releases-1251680599.cos.ap-shanghai.myqcloud.com/production/channels/stable/...
        full_path = f"{cos_prefix}/{path}"

        return f"https://{cos_bucket}.cos.{cos_region}.myqcloud.com/{full_path}"
    
    def get_storage_url(self, path: str) -> str:
        """
        Get storage URL based on app type (CN uses COS, INTL uses S3)
        
        Args:
            path: Path relative to environment prefix
            
        Returns:
            Full storage URL (COS for CN, S3 for INTL)
        """
        if self._is_cn:
            return self.get_cos_url(path)
        else:
            return self.get_s3_url(path)
    
    def get_s3_url(self, path: str) -> str:
        """
        Construct S3 URL for a given path (INTL app only)

        Args:
            path: Path relative to environment prefix (e.g., 'releases/v1.0.0/...')

        Returns:
            Full S3 URL with base path and environment prefix

        Example:
            get_s3_url('releases/v1.0.0/macos/aarch64/eCan.pkg')
            → https://ecan-releases.s3.us-east-1.amazonaws.com/production/releases/v1.0.0/macos/aarch64/eCan.pkg
        """
        if not self.enabled:
            return ""

        # Warn if CN app is trying to use S3
        if self._is_cn:
            logger.warning("[OTA Config] INTL S3 URL requested for CN app, use get_cos_url() instead")

        s3_bucket = self.get_common('s3_bucket', 'ecan-releases')
        s3_region = self.get_common('s3_region', 'us-east-1')
        s3_base_path = self.get_common('s3_base_path', '')
        s3_prefix = self.get_s3_prefix()

        # Combine: bucket + (base_path)? + environment prefix + path
        # With the default empty s3_base_path this yields {prefix}/{path},
        # e.g. production/releases/v1.0.0/... (single ``releases``).
        # When s3_base_path is configured (e.g. "releases") the URL has the
        # form {base_path}/{prefix}/{path}.
        if s3_base_path:
            full_path = f"{s3_base_path}/{s3_prefix}/{path}"
        else:
            full_path = f"{s3_prefix}/{path}"

        return f"https://{s3_bucket}.s3.{s3_region}.amazonaws.com/{full_path}"
    
    def is_cn_app(self) -> bool:
        """Check if running as CN app"""
        return self._is_cn
    
    def is_intl_app(self) -> bool:
        """Check if running as INTL app"""
        return not self._is_cn
    
    def is_dev_mode(self) -> bool:
        """Check if running in development mode"""
        # Check environment variable or configuration
        if os.environ.get('ECAN_DEV_MODE', '').lower() in ['true', '1', 'yes']:
            return True
        return self.environment == 'development' or self.get('dev_mode', False)
    
    def is_signature_required(self) -> bool:
        """Check if signature verification is required"""
        return self.get('signature_required', False)
    
    def is_signature_verification_enabled(self) -> bool:
        """Check if signature verification is enabled"""
        return self.get('signature_verification', self.get('signature_required', False))
    
    def get_public_key_path(self) -> Optional[str]:
        """
        Get public key path for signature verification
        
        Returns:
            Path to public key file, or None if not configured
        """
        # Try to find public key in ota/certificates directory
        current_file = Path(__file__).parent.parent  # Go up to ota directory
        public_key_path = current_file / "certificates" / "ed25519_public_key.pem"
        
        if public_key_path.exists():
            return str(public_key_path)
        
        # Try project root
        current = Path.cwd()
        for _ in range(5):  # Search up to 5 levels
            public_key_path = current / "ota" / "certificates" / "ed25519_public_key.pem"
            if public_key_path.exists():
                return str(public_key_path)
            current = current.parent
        
        logger.warning("[OTA Config] Public key not found, signature verification may fail")
        return None
    
    def is_auto_check_enabled(self) -> bool:
        """Check if auto check is enabled"""
        return self.get('auto_check', True)
    
    def get_check_interval(self) -> int:
        """Get check interval in seconds"""
        return self.get('check_interval', 3600)
    
    def is_silent_mode(self) -> bool:
        """Check if silent mode is enabled"""
        return self.get('silent_mode', False)
    
    def is_http_allowed(self) -> bool:
        """Check if HTTP is allowed (only in dev mode)"""
        return self.is_dev_mode() and self.get('allow_http', True)

    def get_platform_config(self, platform: Optional[str] = None) -> Dict[str, Any]:
        """
        Get platform-specific configuration
        
        Args:
            platform: Platform name (darwin, windows, linux), auto-detect if None
            
        Returns:
            Platform configuration dictionary
        """
        if platform is None:
            import platform as plat
            platform = plat.system().lower()
        
        # Return basic platform config
        return {
            'appcast_url': self.get_appcast_url(platform),
        }
    
    def get_appcast_url_for_arch(self, arch: str) -> str:
        """
        Get appcast URL for current platform and architecture
        
        Args:
            arch: Architecture (aarch64, amd64)
            
        Returns:
            Appcast URL
        """
        import platform
        plat = platform.system().lower()
        if plat == 'darwin':
            return self.get_appcast_url('macos', arch)
        elif plat == 'windows':
            return self.get_appcast_url('windows', arch)
        else:
            return self.get_appcast_url('linux', arch)
    
    def get_full_config(self) -> Dict[str, Any]:
        """
        Get complete configuration for current environment
        
        Returns:
            Dictionary with all configuration values
        """
        if not self.enabled:
            return {'ota_enabled': False}
        
        env = self.environment
        env_config = self._config.get('environments', {}).get(env, {})
        
        return {
            'ota_enabled': True,
            'environment': env,
            'app_id': self._app_id,
            'is_cn': self._is_cn,
            'storage_backend': 'cos' if self._is_cn else 's3',
            's3_bucket': self.get_common('s3_bucket'),
            'cos_bucket': self.get_common('cos_bucket'),
            'appcast_base': env_config.get('appcast_base'),
            'appcast_base_cos': env_config.get('appcast_base_cos'),
            'signature_required': env_config.get('signature_required', False),
            'signature_verification': env_config.get('signature_verification', False),
            'auto_check': env_config.get('auto_check', False),
            'check_interval': env_config.get('check_interval', 3600),
            'silent_mode': env_config.get('silent_mode', False),
            'allow_http': env_config.get('allow_http', False),
            'dev_mode': env_config.get('dev_mode', False),
        }
    
    def __repr__(self) -> str:
        """String representation"""
        if not self.enabled:
            return "OTAConfig(disabled)"
        backend = "COS" if self._is_cn else "S3"
        return f"OTAConfig(app={self._app_id}, backend={backend}, environment={self.environment}, enabled={self.enabled})"


# Global instance
_ota_config: Optional[OTAConfig] = None


def get_ota_config(config_file: Optional[str] = None, reload: bool = False) -> OTAConfig:
    """
    Get global OTA configuration instance
    
    Args:
        config_file: Path to configuration file (optional)
        reload: Force reload configuration
        
    Returns:
        OTAConfig instance
    """
    global _ota_config
    
    if _ota_config is None or reload or config_file is not None:
        _ota_config = OTAConfig(config_file)
    
    return _ota_config


def is_ota_enabled() -> bool:
    """
    Quick check if OTA is enabled
    
    Returns:
        True if OTA is enabled
    """
    return get_ota_config().enabled


# Create global ota_config instance for backward compatibility
ota_config = get_ota_config()
