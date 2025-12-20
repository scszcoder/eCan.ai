#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WebDriver downloader module
"""

import os
import tempfile
import zipfile
import time
from typing import Optional
import asyncio
import ssl
import aiohttp
import aiofiles
import zipfile

from utils.logger_helper import logger_helper as logger
from .config import (get_current_platform, KNOWN_GOOD_VERSIONS_URL,
                    KNOWN_GOOD_VERSIONS_URL_FALLBACK)
from .utils import get_chrome_major_version

class WebDriverDownloader:
    """WebDriver downloader with async support and background download capability"""
    
    def __init__(self):
        pass

        
    async def _get_download_url_from_official_json(self, chrome_version: str) -> Optional[str]:
        """
        Fetches the official JSON data to find the best matching ChromeDriver download URL.
        """
        try:
            logger.info("Fetching official ChromeDriver versions...")
            platform_key = get_current_platform()
            target_major_version = get_chrome_major_version(chrome_version)

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            connector = aiohttp.TCPConnector(ssl=ssl_context)
            async with aiohttp.ClientSession(connector=connector, headers=headers) as session:
                async with session.get(KNOWN_GOOD_VERSIONS_URL) as response:
                    if response.status != 200:
                        logger.error(f"Failed to fetch version data, status: {response.status}")
                        return None
                    data = await response.json()

            # Find the best compatible version
            from packaging.version import parse as parse_version
            target_version = parse_version(chrome_version)

            best_match_url = None
            latest_compatible_version = None
            nearest_match_url = None
            nearest_version = None
            min_version_diff = float('inf')

            # Find the latest version <= user's version
            for version_info in reversed(data.get("versions", [])):
                available_version_str = version_info.get("version")
                if not available_version_str: continue

                available_major = available_version_str.split('.')[0]
                
                if available_major == target_major_version:
                    available_version = parse_version(available_version_str)
                    if available_version <= target_version:
                        downloads = version_info.get("downloads", {}).get("chromedriver", [])
                        for download in downloads:
                            if download.get("platform") == platform_key:
                                best_match_url = download.get("url")
                                latest_compatible_version = available_version_str
                                logger.info(f"Found compatible version: {latest_compatible_version}")
                                break # Found the best one, no need to check older versions
                if best_match_url:
                    break
                
                # Track nearest version as fallback
                try:
                    version_diff = abs(int(available_major) - int(target_major_version))
                    if version_diff < min_version_diff:
                        downloads = version_info.get("downloads", {}).get("chromedriver", [])
                        for download in downloads:
                            if download.get("platform") == platform_key:
                                min_version_diff = version_diff
                                nearest_match_url = download.get("url")
                                nearest_version = available_version_str
                                break
                except (ValueError, TypeError):
                    continue

            if best_match_url:
                logger.info(f"Selected best match URL: {best_match_url}")
                return best_match_url
            elif nearest_match_url:
                logger.warning(f"Exact version {target_major_version} not found, using nearest available version {nearest_version}")
                return nearest_match_url
            else:
                logger.warning(f"Could not find a matching ChromeDriver for version {target_major_version} on platform {platform_key}")
                return None

        except Exception as e:
            logger.error(f"Error finding download URL from official source: {e}")
            return None

    async def _get_download_url_from_npm_mirror(self, chrome_version: str) -> Optional[str]:
        """
        Fetches data from the NPM mirror to find the best matching ChromeDriver download URL.
        """
        try:
            logger.info("Fetching ChromeDriver versions from NPM mirror...")
            platform_key = get_current_platform()
            target_major_version = get_chrome_major_version(chrome_version)

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            connector = aiohttp.TCPConnector(ssl=ssl_context)

            async with aiohttp.ClientSession(connector=connector, headers=headers) as session:
                async with session.get(KNOWN_GOOD_VERSIONS_URL_FALLBACK) as response:
                    if response.status != 200:
                        logger.error(f"Failed to fetch version data from NPM mirror, status: {response.status}")
                        return None
                    data = await response.json()

            from packaging.version import parse as parse_version
            target_version = parse_version(chrome_version)

            best_match_version = None
            nearest_match_version = None
            min_version_diff = float('inf')

            for item in reversed(data):
                version_str = item.get("name", "").strip('/')
                if not version_str: continue

                try:
                    version_major = version_str.split('.')[0]
                    
                    if version_major == target_major_version:
                        available_version = parse_version(version_str)
                        if available_version <= target_version:
                            best_match_version = version_str
                            break
                    
                    # Track nearest version as fallback
                    version_diff = abs(int(version_major) - int(target_major_version))
                    if version_diff < min_version_diff:
                        min_version_diff = version_diff
                        nearest_match_version = version_str
                except (ValueError, TypeError, IndexError):
                    continue

            if best_match_version:
                url = f"{KNOWN_GOOD_VERSIONS_URL_FALLBACK}{best_match_version}/{platform_key}/chromedriver-{platform_key}.zip"
                logger.info(f"Found best match URL from NPM mirror: {url}")
                return url
            elif nearest_match_version:
                url = f"{KNOWN_GOOD_VERSIONS_URL_FALLBACK}{nearest_match_version}/{platform_key}/chromedriver-{platform_key}.zip"
                logger.warning(f"Exact version {target_major_version} not found on NPM mirror, using nearest available version {nearest_match_version}")
                return url
            else:
                logger.warning(f"Could not find a matching ChromeDriver for version {target_major_version} on NPM mirror")
                return None

        except Exception as e:
            logger.error(f"Error finding download URL from NPM mirror: {e}")
            return None

    async def download_webdriver(self, chrome_version: str, target_dir: str) -> Optional[str]:
        """Download matching webdriver for the given Chrome version"""
        try:
            if not chrome_version:
                logger.error("Chrome version not provided, cannot download WebDriver")
                return None

            # Get the download URL from the official JSON endpoint
            download_url = await self._get_download_url_from_official_json(chrome_version)

            if not download_url:
                logger.warning("Official source failed. Trying fallback...")
                download_url = await self._get_download_url_from_npm_mirror(chrome_version)

            if not download_url:
                logger.error("Could not determine a valid download URL from any source.")
                return None

            logger.info(f"Attempting to download from official URL: {download_url}")

            # Use configured temp directory instead of system temp
            from .config import get_temp_dir
            temp_dir = get_temp_dir()
            zip_path = os.path.join(temp_dir, f"chromedriver_{int(time.time())}.zip")

            # Download file with retry
            if await self._download_file_with_retry(download_url, zip_path):
                # Extract file
                platform_key = get_current_platform()
                extract_dir = os.path.join(target_dir, f"chromedriver-{platform_key}")
                os.makedirs(extract_dir, exist_ok=True)

                if self._extract_zip(zip_path, extract_dir):
                    # Get driver path and set permissions
                    driver_path = self._setup_driver(extract_dir)
                    if driver_path:
                        logger.info(f"WebDriver download completed: {driver_path}")
                        return driver_path

            logger.error("All download attempts failed")
            return None

        except Exception as e:
            logger.error(f"WebDriver download failed: {e}")
            return None
    

    
    async def _download_file_with_retry(self, url: str, file_path: str, max_retries: int = 3) -> bool:
        """Download file with retry mechanism"""
        for attempt in range(max_retries):
            try:
                logger.info(f"Download attempt {attempt + 1}/{max_retries}")
                if await self._download_file(url, file_path):
                    return True
            except Exception as e:
                logger.warning(f"Download attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)  # Wait before retry
                    continue
                else:
                    logger.error(f"All download attempts failed for {url}")
                    return False
        return False
    
    async def _download_file(self, url: str, file_path: str) -> bool:
        """Download file from URL"""
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            # Try aiohttp first
            try:
                # Create SSL context that disables certificate verification
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
                connector = aiohttp.TCPConnector(ssl=ssl_context)

                async with aiohttp.ClientSession(connector=connector, headers=headers) as session:
                    async with session.get(url) as response:
                        if response.status != 200:
                            logger.error(f"Download failed, status code: {response.status}")
                            return False
                        
                        async with aiofiles.open(file_path, 'wb') as f:
                            async for chunk in response.content.iter_chunked(8192):
                                await f.write(chunk)
                
                return True
                
            except Exception as aiohttp_error:
                logger.warning(f"aiohttp download failed, trying requests: {aiohttp_error}")
                
                # Fallback to requests if aiohttp fails
                try:
                    import requests
                    from urllib3.exceptions import InsecureRequestWarning
                    requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)
                    
                    response = requests.get(url, verify=False, stream=True, timeout=60, headers=headers)
                    if response.status_code != 200:
                        logger.error(f"Requests download failed, status code: {response.status_code}")
                        return False
                    
                    with open(file_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                    
                    logger.info("Download completed successfully using requests fallback")
                    return True
                    
                except Exception as requests_error:
                    logger.error(f"Both aiohttp and requests failed: {requests_error}")
                    return False
            
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
            
            # First try direct path
            driver_path = os.path.join(extract_dir, driver_name)
            
            # If not found, search in subdirectories (common for ChromeDriver archives)
            if not os.path.exists(driver_path):
                logger.info(f"Driver not found at {driver_path}, searching in subdirectories...")
                
                # Search recursively for chromedriver file
                for root, _, files in os.walk(extract_dir):
                    if driver_name in files:
                        driver_path = os.path.join(root, driver_name)
                        logger.info(f"Found driver at: {driver_path}")
                        break
                else:
                    logger.error(f"Driver file not found in {extract_dir} or subdirectories")
                    return None
            
            # Set execution permissions on non-Windows platforms
            if platform.system() != "Windows":
                os.chmod(driver_path, 0o755)
                logger.info(f"Set execution permissions on: {driver_path}")
            
            return driver_path
            
        except Exception as e:
            logger.error(f"Driver setup failed: {e}")
            return None
    
    def _build_download_url(self, base_url: str, major_version: str, platform_key: str) -> str:
        """Build download URL for the given parameters using smart patterns"""
        # Get the actual Chrome version for more accurate URL building
        from .utils import detect_chrome_version
        actual_version = detect_chrome_version()
        
        # Define URL patterns for each source - Only working sources
        # All sources should download ChromeDriver, not Chrome browser
        url_patterns = {
            "storage.googleapis.com": [
                # Chrome for Testing Public format: /version/platform/chromedriver-platform.zip
                # Based on working example: https://storage.googleapis.com/chrome-for-testing-public/139.0.7258.68/mac-x64/chromedriver-mac-x64.zip
                f"{base_url}{actual_version}/{platform_key}/chromedriver-{platform_key}.zip",
                f"{base_url}{major_version}.0.0/{platform_key}/chromedriver-{platform_key}.zip",
                f"{base_url}{major_version}.0/{platform_key}/chromedriver-{platform_key}.zip",
                f"{base_url}{major_version}/{platform_key}/chromedriver-{platform_key}.zip"
            ],
            "registry.npmmirror.com": [
                # npmmirror format: /-/binary/chrome-for-testing/version/platform/chromedriver-platform.zip
                # Based on working example: https://registry.npmmirror.com/-/binary/chrome-for-testing/141.0.7360.0/mac-x64/chromedriver-mac-x64.zip
                # Try different version formats for npmmirror with dynamic version discovery
                f"https://registry.npmmirror.com/-/binary/chrome-for-testing/{actual_version}/{platform_key}/chromedriver-{platform_key}.zip",
                f"https://registry.npmmirror.com/-/binary/chrome-for-testing/{major_version}.0.0/{platform_key}/chromedriver-{platform_key}.zip",
                f"https://registry.npmmirror.com/-/binary/chrome-for-testing/{major_version}.0/{platform_key}/chromedriver-{platform_key}.zip",
                f"https://registry.npmmirror.com/-/binary/chrome-for-testing/{major_version}/{platform_key}/chromedriver-{platform_key}.zip",
                # Try higher version numbers that might be available
                f"https://registry.npmmirror.com/-/binary/chrome-for-testing/{int(major_version) + 1}.0.0/{platform_key}/chromedriver-{platform_key}.zip",
                f"https://registry.npmmirror.com/-/binary/chrome-for-testing/{int(major_version) + 1}.0/{platform_key}/chromedriver-{platform_key}.zip",
                f"https://registry.npmmirror.com/-/binary/chrome-for-testing/{int(major_version) + 1}/{platform_key}/chromedriver-{platform_key}.zip",
                f"https://registry.npmmirror.com/-/binary/chrome-for-testing/{int(major_version) + 2}.0.0/{platform_key}/chromedriver-{platform_key}.zip",
                f"https://registry.npmmirror.com/-/binary/chrome-for-testing/{int(major_version) + 2}.0/{platform_key}/chromedriver-{platform_key}.zip",
                f"https://registry.npmmirror.com/-/binary/chrome-for-testing/{int(major_version) + 2}/{platform_key}/chromedriver-{platform_key}.zip"
            ]
        }
        
        # Find matching source and return first pattern
        for source_key, patterns in url_patterns.items():
            if source_key in base_url:
                return patterns[0]  # Return first pattern for this source
        
        # Default pattern if no source matches
        return f"{base_url}{major_version}/{platform_key}/chromedriver-{major_version}-{platform_key}.zip"
    

