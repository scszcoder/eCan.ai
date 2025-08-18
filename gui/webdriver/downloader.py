#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WebDriver downloader module
"""

import os
import tempfile
import zipfile
import aiohttp
import aiofiles
from typing import Optional

from utils.logger_helper import logger_helper as logger
from .config import CHROME_FOR_TESTING_DOWNLOAD_URL, get_current_platform
from .utils import get_chrome_major_version

class WebDriverDownloader:
    """WebDriver downloader with async support"""
    
    def __init__(self):
        self._download_base_url = CHROME_FOR_TESTING_DOWNLOAD_URL
        
    async def download_webdriver(self, chrome_version: str, target_dir: str) -> Optional[str]:
        """Download matching webdriver for the given Chrome version"""
        try:
            if not chrome_version:
                logger.error("Chrome version not provided, cannot download WebDriver")
                return None
            
            # Get major version number
            major_version = get_chrome_major_version(chrome_version)
            
            # Build download URL
            platform_key = get_current_platform()
            download_url = f"{self._download_base_url}{major_version}.0.6099.109/{platform_key}/chromedriver-{platform_key}.zip"
            
            logger.info(f"Starting WebDriver download: {download_url}")
            
            # Create temporary directory
            with tempfile.TemporaryDirectory() as temp_dir:
                zip_path = os.path.join(temp_dir, "chromedriver.zip")
                
                # Download file
                if not await self._download_file(download_url, zip_path):
                    return None
                
                # Extract file
                extract_dir = os.path.join(target_dir, f"chromedriver-{platform_key}")
                os.makedirs(extract_dir, exist_ok=True)
                
                if not self._extract_zip(zip_path, extract_dir):
                    return None
                
                # Get driver path and set permissions
                driver_path = self._setup_driver(extract_dir)
                if driver_path:
                    logger.info(f"WebDriver download completed: {driver_path}")
                    return driver_path
                
            return None
                
        except Exception as e:
            logger.error(f"WebDriver download failed: {e}")
            return None
    
    async def _download_file(self, url: str, file_path: str) -> bool:
        """Download file from URL"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        logger.error(f"Download failed, status code: {response.status}")
                        return False
                    
                    async with aiofiles.open(file_path, 'wb') as f:
                        async for chunk in response.content.iter_chunked(8192):
                            await f.write(chunk)
            
            return True
            
        except Exception as e:
            logger.error(f"File download failed: {e}")
            return False
    
    def _extract_zip(self, zip_path: str, extract_dir: str) -> bool:
        """Extract ZIP file"""
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
            return True
            
        except Exception as e:
            logger.error(f"ZIP extraction failed: {e}")
            return False
    
    def _setup_driver(self, extract_dir: str) -> Optional[str]:
        """Setup driver file and set permissions"""
        try:
            import platform
            
            # Get driver name based on platform
            driver_name = "chromedriver.exe" if platform.system() == "Windows" else "chromedriver"
            driver_path = os.path.join(extract_dir, driver_name)
            
            if not os.path.exists(driver_path):
                logger.error(f"Driver file not found: {driver_path}")
                return None
            
            # Set execution permissions on non-Windows platforms
            if platform.system() != "Windows":
                os.chmod(driver_path, 0o755)
            
            return driver_path
            
        except Exception as e:
            logger.error(f"Driver setup failed: {e}")
            return None
    
    def get_download_url(self, chrome_version: str) -> str:
        """Get download URL for the given Chrome version"""
        major_version = get_chrome_major_version(chrome_version)
        platform_key = get_current_platform()
        return f"{self._download_base_url}{major_version}.0.6099.109/{platform_key}/chromedriver-{platform_key}.zip"
