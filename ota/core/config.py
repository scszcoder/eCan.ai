"""
OTA configuration management module
"""

import os
import json
import platform
from pathlib import Path
from typing import Dict, Any, Optional

from utils.logger_helper import logger_helper as logger


class OTAConfig:
    """OTA configuration manager"""
    
    # Constant definitions
    DEFAULT_LOCAL_SERVER_URL = "http://127.0.0.1:8080"
    DEFAULT_REMOTE_SERVER_URL = "https://updates.ecbot.com"
    # S3 configuration - S3_BUCKET needs to be set in GitHub Secrets
    DEFAULT_S3_BUCKET = "ecan-releases"  # Default bucket name, can be overridden by environment variable
    DEFAULT_S3_REGION = "us-east-1"
    
    def __init__(self):
        self.config_file = self._get_config_path()
        self.default_config = {
            "use_local_server": True,  # Whether to use local server
            "local_server_url": self.DEFAULT_LOCAL_SERVER_URL,  # Local server address
            "remote_server_url": self.DEFAULT_REMOTE_SERVER_URL,  # Remote server address
            "check_interval": 300,  # 5 minutes
            "auto_check": True,
            "silent_mode": False,
            "download_path": None,
            "backup_enabled": True,
            "signature_verification": True,   # Enable signature/hash verification
            "signature_required": True,       # Production recommended: fail directly when missing signature/public key/library
            "dev_mode": False,  # Development mode
            "allow_http_in_dev": True,  # Allow HTTP in dev mode
            "force_generic_updater_in_dev": True,  # Force generic updater in dev mode
            "public_key_path": None,  # Digital signature verification public key path
            "ui_update_behavior": "notification", # Options: "notification"(notification only), "dialog"(popup dialog), "badge"(badge only), "notification+badge"(notification+badge)
            # Dev mode installer switch and parameters (disabled by default to avoid accidental execution)
            "dev_installer_enabled": False,
            "dev_installer_quiet": True,
            "dmg_target_dir": "/Applications",
            "platforms": {
                "darwin": {
                    "framework_path": "/Applications/ECBot.app/Contents/Frameworks/Sparkle.framework",
                    # S3 as update source
                    "appcast_url": f"https://{self.DEFAULT_S3_BUCKET}.s3.{self.DEFAULT_S3_REGION}.amazonaws.com/appcast/appcast-macos.xml",
                    "appcast_urls": {
                        "amd64": f"https://{self.DEFAULT_S3_BUCKET}.s3.{self.DEFAULT_S3_REGION}.amazonaws.com/appcast/appcast-macos-amd64.xml",
                        "aarch64": f"https://{self.DEFAULT_S3_BUCKET}.s3.{self.DEFAULT_S3_REGION}.amazonaws.com/appcast/appcast-macos-aarch64.xml"
                    },
                    "local_appcast_url": f"{self.DEFAULT_LOCAL_SERVER_URL}/appcast.xml",
                    "local_appcast_urls": {
                        "amd64": f"{self.DEFAULT_LOCAL_SERVER_URL}/appcast.xml",
                        "aarch64": f"{self.DEFAULT_LOCAL_SERVER_URL}/appcast.xml"
                    }
                },
                "windows": {
                    "dll_path": "winsparkle.dll",
                    # S3 as update source
                    "appcast_url": f"https://{self.DEFAULT_S3_BUCKET}.s3.{self.DEFAULT_S3_REGION}.amazonaws.com/appcast/appcast-windows.xml",
                    "appcast_urls": {
                        "amd64": f"https://{self.DEFAULT_S3_BUCKET}.s3.{self.DEFAULT_S3_REGION}.amazonaws.com/appcast/appcast-windows-amd64.xml",
                        "aarch64": f"https://{self.DEFAULT_S3_BUCKET}.s3.{self.DEFAULT_S3_REGION}.amazonaws.com/appcast/appcast-windows-aarch64.xml"
                    },
                    "local_appcast_url": f"{self.DEFAULT_LOCAL_SERVER_URL}/appcast.xml",
                    "local_appcast_urls": {
                        "amd64": f"{self.DEFAULT_LOCAL_SERVER_URL}/appcast.xml",
                        "aarch64": f"{self.DEFAULT_LOCAL_SERVER_URL}/appcast.xml"
                    }
                },
                "linux": {
                    "api_url": "https://updates.ecbot.com/api",
                    "download_dir": "/tmp/ecbot_updates",
                    # S3 as update source
                    "appcast_url": f"https://{self.DEFAULT_S3_BUCKET}.s3.{self.DEFAULT_S3_REGION}.amazonaws.com/appcast/appcast-linux.xml",
                    "appcast_urls": {
                        "amd64": f"https://{self.DEFAULT_S3_BUCKET}.s3.{self.DEFAULT_S3_REGION}.amazonaws.com/appcast/appcast-linux-amd64.xml",
                        "aarch64": f"https://{self.DEFAULT_S3_BUCKET}.s3.{self.DEFAULT_S3_REGION}.amazonaws.com/appcast/appcast-linux-aarch64.xml"
                    },
                    "local_appcast_url": f"{self.DEFAULT_LOCAL_SERVER_URL}/appcast.xml",
                    "local_appcast_urls": {
                        "amd64": f"{self.DEFAULT_LOCAL_SERVER_URL}/appcast.xml",
                        "aarch64": f"{self.DEFAULT_LOCAL_SERVER_URL}/appcast.xml"
                    }
                }
            }
        }
        self.config = self._load_config()
        # Automatically clean up deprecated configuration items
        self.cleanup_deprecated_config()

    def _get_config_path(self) -> Path:
        """Get configuration file path"""
        if platform.system() == "Darwin":
            config_dir = Path.home() / "Library/Application Support/ECBot"
        elif platform.system() == "Windows":
            config_dir = Path.home() / "AppData/Local/ECBot"
        else:
            config_dir = Path.home() / ".config/ecbot"
        
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir / "ota_config.json"
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration"""
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    # Merge default configuration
                    return self._merge_config(self.default_config, config)
            else:
                return self.default_config.copy()
        except Exception as e:
            logger.error(f"Failed to load OTA config: {e}")
            return self.default_config.copy()
    
    def _merge_config(self, default: Dict, user: Dict) -> Dict:
        """Merge configuration"""
        result = default.copy()
        for key, value in user.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_config(result[key], value)
            else:
                result[key] = value
        return result
    
    def save_config(self):
        """Save configuration"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
            logger.info("OTA config saved successfully")
        except Exception as e:
            logger.error(f"Failed to save OTA config: {e}")
    
    def get(self, key: str, default=None):
        """Get configuration value"""
        keys = key.split('.')
        value = self.config
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value
    
    def set(self, key: str, value: Any):
        """Set configuration value"""
        keys = key.split('.')
        config = self.config
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        config[keys[-1]] = value
        self.save_config()
    
    def get_platform_config(self) -> Dict[str, Any]:
        """Get current platform configuration"""
        platform_name = platform.system().lower()
        return self.config.get("platforms", {}).get(platform_name, {})
    
    def get_update_server(self) -> str:
        """Get update server URL.

        Supports both the new local/remote server switching and legacy keys
        like ``update_server`` / ``dev_update_server`` for backward
        compatibility (tests and existing configs).
        """
        # 1) Explicit legacy override takes highest precedence
        direct_url = self.config.get("update_server")
        if direct_url:
            return direct_url

        # 2) Dev-specific override
        if self.is_dev_mode():
            dev_url = self.config.get("dev_update_server")
            if dev_url:
                return dev_url

        # 3) Local server or dev mode uses local_server_url
        if self.config.get("use_local_server", False) or self.is_dev_mode():
            return self.config.get("local_server_url", self.DEFAULT_LOCAL_SERVER_URL)

        # 4) Default to remote server URL
        return self.config.get("remote_server_url", self.DEFAULT_REMOTE_SERVER_URL)

    def get_check_interval(self) -> int:
        """Get check interval (seconds)"""
        return self.config.get("check_interval", 3600)
    
    def is_auto_check_enabled(self) -> bool:
        """Whether auto check is enabled"""
        return self.config.get("auto_check", True)
    
    def is_silent_mode(self) -> bool:
        """Whether silent mode is enabled"""
        return self.config.get("silent_mode", False)
    
    def is_backup_enabled(self) -> bool:
        """Whether backup is enabled"""
        return self.config.get("backup_enabled", True)
    
    def is_signature_verification_enabled(self) -> bool:
        """Whether signature verification is enabled"""
        return self.config.get("signature_verification", True)
    
    def is_dev_mode(self) -> bool:
        """Whether in development mode"""
        # Check environment variables or configuration
        return (os.environ.get('ECBOT_DEV_MODE', '').lower() in ['true', '1', 'yes'] or 
                self.config.get("dev_mode", False))
    
    def is_http_allowed(self) -> bool:
        """Whether HTTP is allowed (only in dev mode)"""
        return self.is_dev_mode() and self.config.get("allow_http_in_dev", True)
    
    def get_public_key_path(self) -> Optional[str]:
        """Simplified public key path retrieval"""
        # Prioritize path from configuration file
        config_path = self.config.get("public_key_path")
        if config_path and os.path.exists(config_path):
            return config_path
        
        # Simplified default path search
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        default_paths = [
            os.path.join(project_root, "ota", "certificates", "ed25519_public_key.pem"),
            os.path.join(project_root, "keys", "public_key.pem")
        ]
        
        for path in default_paths:
            if os.path.exists(path):
                logger.info(f"Found public key at default location: {path}")
                return path
        
        logger.warning("No public key found")
        return None
    
    def get_appcast_url(self, arch: str = None) -> str:
        """Get appcast URL based on current server configuration"""
        platform_config = self.get_platform_config()
        
        # If using local server
        if self.config.get("use_local_server", False):
            if arch and "local_appcast_urls" in platform_config:
                return platform_config["local_appcast_urls"].get(arch, platform_config.get("local_appcast_url", f"{self.DEFAULT_LOCAL_SERVER_URL}/appcast.xml"))
            return platform_config.get("local_appcast_url", f"{self.DEFAULT_LOCAL_SERVER_URL}/appcast.xml")
        
        # Use remote server
        if arch and "appcast_urls" in platform_config:
            return platform_config["appcast_urls"].get(arch, platform_config.get("appcast_url", ""))
        return platform_config.get("appcast_url", "")
    
    def set_use_local_server(self, use_local: bool):
        """Set whether to use local server"""
        self.config["use_local_server"] = use_local
        self.save_config()
        logger.info(f"Update server switched to: {'local' if use_local else 'remote'}")
    
    def is_using_local_server(self) -> bool:
        """Check if using local server"""
        return self.config.get("use_local_server", False)
    
    def set_local_server_url(self, url: str):
        """Set local server URL"""
        self.config["local_server_url"] = url
        self.save_config()
        logger.info(f"Local server URL set to: {url}")
    
    def set_remote_server_url(self, url: str):
        """Set remote server URL"""
        self.config["remote_server_url"] = url
        self.save_config()
        logger.info(f"Remote server URL set to: {url}")
    
    def cleanup_deprecated_config(self):
        """Clean up deprecated configuration items"""
        deprecated_keys = ["update_server", "dev_update_server"]
        cleaned = False
        
        for key in deprecated_keys:
            if key in self.config:
                del self.config[key]
                cleaned = True
                logger.info(f"Removed deprecated config key: {key}")
        
        if cleaned:
            self.save_config()
            logger.info("Deprecated configuration items cleaned up")

    def validate_config(self) -> bool:
        """Simplified configuration validation"""
        # Only validate the most critical configuration
        update_server = self.get_update_server()
        if not update_server or not (update_server.startswith('http://') or update_server.startswith('https://')):
            logger.error("Invalid update server URL")
            return False
        
        logger.info("Configuration validation passed")
        return True
    
    # Removed get_secure_config method - over-implementation


# Global configuration instance
ota_config = OTAConfig()

# Validate configuration at startup
if not ota_config.validate_config():
    logger.warning("OTA configuration validation failed - some features may not work correctly")