#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WebDriver cache manager for efficient storage and retrieval
"""

import os
import json
import hashlib
import shutil
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from pathlib import Path

from utils.logger_helper import logger_helper as logger
from .config import get_cache_dir, get_metadata_file, get_webdriver_dir


class WebDriverCache:
    """WebDriver cache manager with metadata tracking"""
    
    def __init__(self):
        self._cache_dir = get_cache_dir()
        self._metadata_file = get_metadata_file()
        self._metadata = self._load_metadata()
        
        # Ensure cache directory exists
        os.makedirs(self._cache_dir, exist_ok=True)
    
    def _load_metadata(self) -> Dict[str, Any]:
        """Load cache metadata from file"""
        try:
            if os.path.exists(self._metadata_file):
                with open(self._metadata_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load cache metadata: {e}")
        
        return {
            "webdrivers": {},
            "last_cleanup": None,
            "cache_info": {
                "created": datetime.now().isoformat(),
                "version": "1.0"
            }
        }
    
    def _save_metadata(self):
        """Save cache metadata to file"""
        try:
            with open(self._metadata_file, 'w', encoding='utf-8') as f:
                json.dump(self._metadata, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save cache metadata: {e}")
    
    def get_cached_webdriver(self, chrome_version: str, platform: str) -> Optional[str]:
        """Get cached WebDriver path if available and valid"""
        try:
            cache_key = f"{chrome_version}_{platform}"
            cached_info = self._metadata["webdrivers"].get(cache_key)
            
            if not cached_info:
                return None
            
            # Check if cached file still exists
            cached_path = cached_info.get("path")
            if not cached_path or not os.path.exists(cached_path):
                # Remove invalid cache entry
                del self._metadata["webdrivers"][cache_key]
                self._save_metadata()
                return None
            
            # Check if cache is still valid (not expired)
            if self._is_cache_expired(cached_info):
                logger.info(f"Cache expired for {cache_key}")
                return None
            
            # Check file integrity
            if not self._verify_file_integrity(cached_path, cached_info.get("checksum")):
                logger.warning(f"File integrity check failed for {cached_path}")
                return None
            
            logger.info(f"Using cached WebDriver: {cached_path}")
            return cached_path
            
        except Exception as e:
            logger.error(f"Error checking cache: {e}")
            return None
    
    def cache_webdriver(self, chrome_version: str, platform: str, file_path: str) -> bool:
        """Cache a WebDriver file with metadata"""
        try:
            if not os.path.exists(file_path):
                logger.error(f"File does not exist: {file_path}")
                return False
            
            # Calculate file checksum
            checksum = self._calculate_file_checksum(file_path)
            
            # Get file info
            file_stat = os.stat(file_path)
            file_size = file_stat.st_size
            
            # Create cache entry
            cache_key = f"{chrome_version}_{platform}"
            cache_entry = {
                "path": file_path,
                "checksum": checksum,
                "size": file_size,
                "cached_at": datetime.now().isoformat(),
                "chrome_version": chrome_version,
                "platform": platform,
                "expires_at": (datetime.now() + timedelta(days=30)).isoformat()  # 30 days cache
            }
            
            # Update metadata
            self._metadata["webdrivers"][cache_key] = cache_entry
            self._save_metadata()
            
            logger.info(f"WebDriver cached successfully: {cache_key}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to cache WebDriver: {e}")
            return False
    
    def _is_cache_expired(self, cache_info: Dict[str, Any]) -> bool:
        """Check if cache entry is expired"""
        try:
            expires_at = cache_info.get("expires_at")
            if not expires_at:
                return True
            
            expiry_date = datetime.fromisoformat(expires_at)
            return datetime.now() > expiry_date
            
        except Exception as e:
            logger.warning(f"Error checking cache expiration: {e}")
            return True
    
    def _calculate_file_checksum(self, file_path: str) -> str:
        """Calculate SHA256 checksum of file"""
        try:
            hash_sha256 = hashlib.sha256()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_sha256.update(chunk)
            return hash_sha256.hexdigest()
        except Exception as e:
            logger.error(f"Failed to calculate checksum: {e}")
            return ""
    
    def _verify_file_integrity(self, file_path: str, expected_checksum: str) -> bool:
        """Verify file integrity using checksum"""
        if not expected_checksum:
            return False
        
        actual_checksum = self._calculate_file_checksum(file_path)
        return actual_checksum == expected_checksum
    
    def cleanup_expired_cache(self) -> int:
        """Clean up expired cache entries and files"""
        try:
            cleaned_count = 0
            expired_keys = []
            
            for cache_key, cache_info in self._metadata["webdrivers"].items():
                if self._is_cache_expired(cache_info):
                    expired_keys.append(cache_key)
                    
                    # Remove expired file
                    file_path = cache_info.get("path")
                    if file_path and os.path.exists(file_path):
                        try:
                            os.remove(file_path)
                            cleaned_count += 1
                            logger.info(f"Removed expired cache file: {file_path}")
                        except Exception as e:
                            logger.warning(f"Failed to remove expired file {file_path}: {e}")
            
            # Remove expired entries from metadata
            for key in expired_keys:
                del self._metadata["webdrivers"][key]
            
            if expired_keys:
                self._metadata["last_cleanup"] = datetime.now().isoformat()
                self._save_metadata()
                logger.info(f"Cleaned up {cleaned_count} expired cache entries")
            
            return cleaned_count
            
        except Exception as e:
            logger.error(f"Cache cleanup failed: {e}")
            return 0
    
    def get_cache_info(self) -> Dict[str, Any]:
        """Get cache statistics and information"""
        try:
            total_files = len(self._metadata["webdrivers"])
            total_size = sum(info.get("size", 0) for info in self._metadata["webdrivers"].values())
            
            return {
                "total_cached_files": total_files,
                "total_cache_size_bytes": total_size,
                "total_cache_size_mb": round(total_size / (1024 * 1024), 2),
                "last_cleanup": self._metadata.get("last_cleanup"),
                "cache_created": self._metadata.get("cache_info", {}).get("created"),
                "cache_version": self._metadata.get("cache_info", {}).get("version")
            }
        except Exception as e:
            logger.error(f"Failed to get cache info: {e}")
            return {}
    
    def clear_all_cache(self) -> bool:
        """Clear all cached WebDriver files"""
        try:
            # Remove all cached files
            for cache_info in self._metadata["webdrivers"].values():
                file_path = cache_info.get("path")
                if file_path and os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except Exception as e:
                        logger.warning(f"Failed to remove cache file {file_path}: {e}")
            
            # Clear metadata
            self._metadata["webdrivers"] = {}
            self._save_metadata()
            
            logger.info("All cache cleared successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to clear cache: {e}")
            return False
