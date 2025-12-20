"""
OTA Version Ignore Manager
Manages versions that users choose to ignore ("Don't remind me again")
"""

import json
import os
from pathlib import Path
from typing import Set
from utils.logger_helper import logger_helper as logger


class VersionIgnoreManager:
    """Manages ignored OTA versions"""
    
    def __init__(self, config_dir: str = None):
        """Initialize version ignore manager
        
        Args:
            config_dir: Configuration directory, defaults to user data directory
        """
        if config_dir is None:
            from config.envi import getECBotDataHome
            config_dir = getECBotDataHome()
        
        self.config_file = Path(config_dir) / "ota_ignored_versions.json"
        self.ignored_versions: Set[str] = set()
        self._load()
    
    def _load(self):
        """Load ignored version list from file"""
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.ignored_versions = set(data.get('ignored_versions', []))
                logger.info(f"[OTA] Loaded {len(self.ignored_versions)} ignored versions")
            else:
                logger.info("[OTA] No ignored versions file found, starting fresh")
        except Exception as e:
            logger.error(f"[OTA] Failed to load ignored versions: {e}")
            self.ignored_versions = set()
    
    def _save(self):
        """Save ignored version list to file"""
        try:
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'ignored_versions': list(self.ignored_versions)
                }, f, indent=2, ensure_ascii=False)
            logger.info(f"[OTA] Saved {len(self.ignored_versions)} ignored versions")
        except Exception as e:
            logger.error(f"[OTA] Failed to save ignored versions: {e}")
    
    def ignore_version(self, version: str):
        """Add version to ignore list
        
        Args:
            version: Version number to ignore
        """
        if version and version not in self.ignored_versions:
            self.ignored_versions.add(version)
            self._save()
            logger.info(f"[OTA] Version {version} added to ignore list")
    
    def unignore_version(self, version: str):
        """Remove version from ignore list
        
        Args:
            version: Version number to remove
        """
        if version in self.ignored_versions:
            self.ignored_versions.remove(version)
            self._save()
            logger.info(f"[OTA] Version {version} removed from ignore list")
    
    def is_ignored(self, version: str) -> bool:
        """Check if version is ignored
        
        Args:
            version: Version number to check
            
        Returns:
            True if version is ignored, False otherwise
        """
        return version in self.ignored_versions
    
    def clear_all(self):
        """Clear all ignored versions"""
        self.ignored_versions.clear()
        self._save()
        logger.info("[OTA] Cleared all ignored versions")
    
    def get_ignored_versions(self) -> list:
        """Get list of all ignored versions
        
        Returns:
            List of ignored versions
        """
        return sorted(list(self.ignored_versions))


# Global singleton
_version_ignore_manager = None


def get_version_ignore_manager() -> VersionIgnoreManager:
    """Get global version ignore manager singleton
    
    Returns:
        VersionIgnoreManager instance
    """
    global _version_ignore_manager
    if _version_ignore_manager is None:
        _version_ignore_manager = VersionIgnoreManager()
    return _version_ignore_manager
