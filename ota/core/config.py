"""
OTA配置管理模块
"""

import os
import json
import platform
from pathlib import Path
from typing import Dict, Any, Optional

from utils.logger_helper import logger_helper as logger


class OTAConfig:
    """OTA配置管理器"""
    
    def __init__(self):
        self.config_file = self._get_config_path()
        self.default_config = {
            "update_server": "https://updates.ecbot.com",
            "check_interval": 3600,  # 1小时
            "auto_check": True,
            "silent_mode": False,
            "download_path": None,
            "backup_enabled": True,
            "signature_verification": True,
            "platforms": {
                "darwin": {
                    "framework_path": "/Applications/ECBot.app/Contents/Frameworks/Sparkle.framework",
                    "appcast_url": "https://updates.ecbot.com/appcast.xml"
                },
                "windows": {
                    "dll_path": "winsparkle.dll",
                    "appcast_url": "https://updates.ecbot.com/appcast.xml"
                },
                "linux": {
                    "api_url": "https://updates.ecbot.com/api",
                    "download_dir": "/tmp/ecbot_updates"
                }
            }
        }
        self.config = self._load_config()
    
    def _get_config_path(self) -> Path:
        """获取配置文件路径"""
        if platform.system() == "Darwin":
            config_dir = Path.home() / "Library/Application Support/ECBot"
        elif platform.system() == "Windows":
            config_dir = Path.home() / "AppData/Local/ECBot"
        else:
            config_dir = Path.home() / ".config/ecbot"
        
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir / "ota_config.json"
    
    def _load_config(self) -> Dict[str, Any]:
        """加载配置"""
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    # 合并默认配置
                    return self._merge_config(self.default_config, config)
            else:
                return self.default_config.copy()
        except Exception as e:
            logger.error(f"Failed to load OTA config: {e}")
            return self.default_config.copy()
    
    def _merge_config(self, default: Dict, user: Dict) -> Dict:
        """合并配置"""
        result = default.copy()
        for key, value in user.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_config(result[key], value)
            else:
                result[key] = value
        return result
    
    def save_config(self):
        """保存配置"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
            logger.info("OTA config saved successfully")
        except Exception as e:
            logger.error(f"Failed to save OTA config: {e}")
    
    def get(self, key: str, default=None):
        """获取配置值"""
        keys = key.split('.')
        value = self.config
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value
    
    def set(self, key: str, value: Any):
        """设置配置值"""
        keys = key.split('.')
        config = self.config
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        config[keys[-1]] = value
        self.save_config()
    
    def get_platform_config(self) -> Dict[str, Any]:
        """获取当前平台配置"""
        platform_name = platform.system().lower()
        return self.config.get("platforms", {}).get(platform_name, {})
    
    def get_update_server(self) -> str:
        """获取更新服务器URL"""
        return self.config.get("update_server", "https://updates.ecbot.com")
    
    def get_check_interval(self) -> int:
        """获取检查间隔（秒）"""
        return self.config.get("check_interval", 3600)
    
    def is_auto_check_enabled(self) -> bool:
        """是否启用自动检查"""
        return self.config.get("auto_check", True)
    
    def is_silent_mode(self) -> bool:
        """是否静默模式"""
        return self.config.get("silent_mode", False)
    
    def is_backup_enabled(self) -> bool:
        """是否启用备份"""
        return self.config.get("backup_enabled", True)
    
    def is_signature_verification_enabled(self) -> bool:
        """是否启用签名验证"""
        return self.config.get("signature_verification", True)


# 全局配置实例
ota_config = OTAConfig() 