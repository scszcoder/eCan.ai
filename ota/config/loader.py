"""
Simple OTA Configuration Loader
Loads configuration from ota_config.yaml
"""

import os
import yaml
from pathlib import Path
from typing import Any, Optional, Dict
from utils.logger_helper import logger_helper as logger


class OTAConfig:
    """Simple OTA configuration loader"""
    
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
        
        if self.enabled:
            logger.info(f"[OTA Config] Loaded configuration from {config_file}")
            logger.info(f"[OTA Config] Environment: {self.environment}")
            logger.info(f"[OTA Config] OTA Server: {self.get('ota_server')}")
            logger.info(f"[OTA Config] S3 Bucket: {self.get('s3_bucket')}")
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
    
    def get_appcast_url(self, platform: str, arch: Optional[str] = None, language: Optional[str] = None) -> str:
        """
        Get appcast URL for platform and architecture (with i18n support)
        
        Args:
            platform: Platform name (macos, windows, linux)
            arch: Architecture (aarch64, amd64), optional
            language: Language code (e.g., 'en-US', 'zh-CN'), optional
            
        Returns:
            Appcast URL
            
        Example:
            get_appcast_url('macos', 'aarch64')
            → https://ecan-updates.s3.us-east-1.amazonaws.com/production/channels/stable/appcast-macos-aarch64.xml
            
            get_appcast_url('macos', 'aarch64', 'zh-CN')
            → https://ecan-updates.s3.us-east-1.amazonaws.com/production/channels/stable/appcast-macos-aarch64.zh-CN.xml
        """
        if not self.enabled:
            return ""
        
        # Get channel for current environment
        channel = self.get_channel()
        
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
        
        # Use S3 URL with channel path
        return self.get_s3_url(f"channels/{channel}/{filename}")
    
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
    
    def get_s3_url(self, path: str) -> str:
        """
        Construct S3 URL for a given path
        
        Args:
            path: Path relative to environment prefix (e.g., 'releases/v1.0.0/...')
            
        Returns:
            Full S3 URL with base path and environment prefix
            
        Example:
            get_s3_url('releases/v1.0.0/macos/aarch64/eCan.pkg')
            → https://ecan-releases.s3.us-east-1.amazonaws.com/releases/production/releases/v1.0.0/macos/aarch64/eCan.pkg
        """
        if not self.enabled:
            return ""
        
        s3_bucket = self.get_common('s3_bucket', 'ecan-releases')
        s3_region = self.get_common('s3_region', 'us-east-1')
        s3_base_path = self.get_common('s3_base_path', '')
        s3_prefix = self.get_s3_prefix()
        
        # Combine: bucket + base_path + environment prefix + path
        # Example: ecan-releases/releases/production/releases/v1.0.0/...
        if s3_base_path:
            full_path = f"{s3_base_path}/{s3_prefix}/{path}"
        else:
            full_path = f"{s3_prefix}/{path}"
        
        return f"https://{s3_bucket}.s3.{s3_region}.amazonaws.com/{full_path}"
    
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
    
    def get_update_server(self) -> str:
        """Get update server URL"""
        return self.get('ota_server', '')
    
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
            'ota_server': self.get_update_server(),
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
            'ota_server': env_config.get('ota_server'),
            's3_bucket': env_config.get('s3_bucket'),
            'appcast_base': env_config.get('appcast_base'),
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
        return f"OTAConfig(environment={self.environment}, enabled={self.enabled})"


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


def validate_config() -> bool:
    """
    Validate OTA configuration
    
    Returns:
        True if configuration is valid
    """
    config = get_ota_config()
    if not config.enabled:
        return False
    
    # Check if update server is valid
    update_server = config.get_update_server()
    if not update_server or not (update_server.startswith('http://') or update_server.startswith('https://')):
        logger.error("[OTA Config] Invalid update server URL")
        return False
    
    logger.info("[OTA Config] Configuration validation passed")
    return True
