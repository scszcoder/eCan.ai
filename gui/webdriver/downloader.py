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
import threading
import time
from typing import Optional, Callable
from concurrent.futures import ThreadPoolExecutor
import asyncio

from utils.logger_helper import logger_helper as logger
from .config import CHROME_FOR_TESTING_DOWNLOAD_URL, ALTERNATIVE_DOWNLOAD_URLS, get_current_platform, SSL_VERIFY, SSL_CHECK_HOSTNAME
from .utils import get_chrome_major_version

class WebDriverDownloader:
    """WebDriver downloader with async support and background download capability"""
    
    def __init__(self):
        self._download_base_url = CHROME_FOR_TESTING_DOWNLOAD_URL
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="WebDriverDownloader")
        self._download_threads = {}
        self._download_status = {}
        
    async def download_webdriver(self, chrome_version: str, target_dir: str) -> Optional[str]:
        """Download matching webdriver for the given Chrome version"""
        try:
            if not chrome_version:
                logger.error("Chrome version not provided, cannot download WebDriver")
                return None
            
            # Get major version number
            major_version = get_chrome_major_version(chrome_version)
            platform_key = get_current_platform()
            
            # Try multiple download sources with retry mechanism
            for base_url in ALTERNATIVE_DOWNLOAD_URLS:
                try:
                    # Use dynamic version discovery for better URL matching
                    download_url = self._build_download_url_with_discovery(base_url, major_version, platform_key)
                    logger.info(f"Trying download from: {base_url}")
                    logger.info(f"Built download URL (with discovery): {download_url}")
                    logger.info(f"Chrome major version: {major_version}, Platform: {platform_key}")
                    
                    # Use configured temp directory instead of system temp
                    from .config import get_temp_dir
                    temp_dir = get_temp_dir()
                    zip_path = os.path.join(temp_dir, f"chromedriver_{int(time.time())}.zip")
                    
                    # Download file with retry
                    if await self._download_file_with_retry(download_url, zip_path):
                        # Extract file
                        extract_dir = os.path.join(target_dir, f"chromedriver-{platform_key}")
                        os.makedirs(extract_dir, exist_ok=True)
                        
                        if self._extract_zip(zip_path, extract_dir):
                            # Get driver path and set permissions
                            driver_path = self._setup_driver(extract_dir)
                            if driver_path:
                                logger.info(f"WebDriver download completed from {base_url}: {driver_path}")
                                return driver_path
                
                except Exception as e:
                    logger.warning(f"Download from {base_url} failed: {e}")
                    continue
            
            logger.error("All download sources failed")
            return None
                
        except Exception as e:
            logger.error(f"WebDriver download failed: {e}")
            return None
    
    def start_background_download(self, chrome_version: str, target_dir: str, 
                                progress_callback: Optional[Callable] = None) -> str:
        """Start WebDriver download in background thread"""
        download_id = f"download_{int(time.time())}"
        
        def download_worker():
            try:
                logger.info(f"Starting background download {download_id}")
                self._download_status[download_id] = {
                    "status": "running",
                    "progress": 0,
                    "message": "Initializing download..."
                }
                
                # Run async download in thread
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                try:
                    result = loop.run_until_complete(
                        self._download_webdriver_sync(chrome_version, target_dir, progress_callback)
                    )
                    
                    if result:
                        self._download_status[download_id] = {
                            "status": "completed",
                            "progress": 100,
                            "message": "Download completed successfully",
                            "result": result
                        }
                        logger.info(f"Background download {download_id} completed: {result}")
                    else:
                        self._download_status[download_id] = {
                            "status": "failed",
                            "progress": 0,
                            "message": "Download failed"
                        }
                        logger.error(f"Background download {download_id} failed")
                        
                finally:
                    loop.close()
                    
            except Exception as e:
                logger.error(f"Background download {download_id} error: {e}")
                self._download_status[download_id] = {
                    "status": "error",
                    "progress": 0,
                    "message": f"Download error: {str(e)}"
                }
        
        # Start download in background thread
        thread = threading.Thread(target=download_worker, name=f"WebDriverDownload_{download_id}")
        thread.daemon = True
        thread.start()
        
        self._download_threads[download_id] = thread
        
        logger.info(f"Background download {download_id} started")
        return download_id
    
    def get_download_status(self, download_id: str) -> Optional[dict]:
        """Get status of background download"""
        return self._download_status.get(download_id)
    
    def wait_for_download(self, download_id: str, timeout: float = None) -> Optional[str]:
        """Wait for background download to complete"""
        if download_id not in self._download_threads:
            return None
            
        thread = self._download_threads[download_id]
        thread.join(timeout=timeout)
        
        if thread.is_alive():
            return None
            
        status = self._download_status.get(download_id, {})
        return status.get("result") if status.get("status") == "completed" else None
    
    async def _download_webdriver_sync(self, chrome_version: str, target_dir: str, 
                                     progress_callback: Optional[Callable] = None) -> Optional[str]:
        """Internal method for sync download (runs in thread)"""
        try:
            if not chrome_version:
                logger.error("Chrome version not provided, cannot download WebDriver")
                return None
            
            # Get major version number
            major_version = get_chrome_major_version(chrome_version)
            platform_key = get_current_platform()
            
            # Try multiple download sources
            for base_url in ALTERNATIVE_DOWNLOAD_URLS:
                try:
                    # Use dynamic version discovery for better URL matching
                    download_url = self._build_download_url_with_discovery(base_url, major_version, platform_key)
                    logger.info(f"Trying download from: {base_url}")
                    logger.info(f"Built download URL (with discovery): {download_url}")
                    logger.info(f"Chrome major version: {major_version}, Platform: {platform_key}")
                    
                    if progress_callback:
                        progress_callback(25, f"Trying download from: {base_url}")
                    
                    # Use configured temp directory instead of system temp
                    from .config import get_temp_dir
                    temp_dir = get_temp_dir()
                    zip_path = os.path.join(temp_dir, f"chromedriver_{int(time.time())}.zip")
                    
                    # Download file
                    if await self._download_file_with_retry_sync(download_url, zip_path, progress_callback):
                        if progress_callback:
                            progress_callback(75, "Extracting downloaded file...")
                        
                        # Extract file
                        extract_dir = os.path.join(target_dir, f"chromedriver-{platform_key}")
                        os.makedirs(extract_dir, exist_ok=True)
                        
                        if self._extract_zip(zip_path, extract_dir):
                            if progress_callback:
                                progress_callback(90, "Setting up WebDriver...")
                            
                            # Get driver path and set permissions
                            driver_path = self._setup_driver(extract_dir)
                            if driver_path:
                                if progress_callback:
                                    progress_callback(100, "Download completed successfully")
                                
                                logger.info(f"WebDriver download completed from {base_url}: {driver_path}")
                                return driver_path
                
                except Exception as e:
                    logger.warning(f"Download from {base_url} failed: {e}")
                    if progress_callback:
                        progress_callback(0, f"Download failed from {base_url}: {str(e)}")
                    continue
            
            logger.error("All download sources failed")
            return None
                
        except Exception as e:
            logger.error(f"WebDriver download failed: {e}")
            return None
    
    async def _download_file_with_retry_sync(self, url: str, file_path: str, 
                                           progress_callback: Optional[Callable] = None,
                                           max_retries: int = 3) -> bool:
        """Download file with retry mechanism (sync version)"""
        for attempt in range(max_retries):
            try:
                logger.info(f"Download attempt {attempt + 1}/{max_retries}")
                if progress_callback:
                    progress_callback(25 + (attempt * 15), f"Download attempt {attempt + 1}/{max_retries}")
                
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
            # Try aiohttp first
            try:
                # Create SSL context based on configuration
                import ssl
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = SSL_CHECK_HOSTNAME
                ssl_context.verify_mode = ssl.CERT_NONE if not SSL_VERIFY else ssl.CERT_REQUIRED
                
                # Create connector with SSL context
                connector = aiohttp.TCPConnector(ssl=ssl_context)
                
                async with aiohttp.ClientSession(connector=connector) as session:
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
                    
                    response = requests.get(url, verify=False, stream=True, timeout=60)
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
                for root, dirs, files in os.walk(extract_dir):
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
    
    def get_download_url(self, chrome_version: str) -> str:
        """Get download URL for the given Chrome version"""
        major_version = get_chrome_major_version(chrome_version)
        platform_key = get_current_platform()
        return self._build_download_url(self._download_base_url, major_version, platform_key)
    
    async def discover_available_versions(self, base_url: str, platform_key: str) -> list:
        """Discover available ChromeDriver versions for a given source"""
        try:
            import requests
            from urllib3.exceptions import InsecureRequestWarning
            requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)
            
            available_versions = []
            
            # Try different version patterns to discover available versions
            version_patterns = [
                "139.0.7258.128",  # Current Chrome version
                "139.0.7258.68",   # Known working version
                "141.0.7360.0",    # Known working npmmirror version
                "139.0.0.0",       # Major version with zeros
                "139.0.0",         # Major version with zeros
                "139",             # Just major version
            ]
            
            for version in version_patterns:
                if "npmmirror.com" in base_url:
                    test_url = f"https://registry.npmmirror.com/-/binary/chrome-for-testing/{version}/{platform_key}/chromedriver-{platform_key}.zip"
                elif "storage.googleapis.com" in base_url:
                    test_url = f"{base_url}{version}/{platform_key}/chromedriver-{platform_key}.zip"
                else:
                    test_url = f"{base_url}{version}/chromedriver_{platform_key}.zip"
                
                try:
                    response = requests.head(test_url, verify=False, timeout=10)
                    if response.status_code in [200, 302]:  # 200 OK or 302 Redirect
                        available_versions.append(version)
                        logger.info(f"✅ found avaiable version: {version} at {test_url}")
                except:
                    continue
            
            return available_versions
            
        except Exception as e:
            logger.warning(f"found version failed: {e}")
            return []
    
    def _build_download_url_with_discovery(self, base_url: str, major_version: str, platform_key: str) -> str:
        """Build download URL with dynamic version discovery"""
        # First try the current Chrome version
        current_url = self._build_download_url(base_url, major_version, platform_key)
        
        # Try to discover available versions
        try:
            # Run discovery in a thread to avoid event loop issues
            import concurrent.futures
            import asyncio
            
            def run_discovery():
                try:
                    # Create new event loop for this thread
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        available_versions = loop.run_until_complete(self.discover_available_versions(base_url, platform_key))
                        return available_versions
                    finally:
                        loop.close()
                except Exception as e:
                    print(f"版本发现在线程中失败: {e}")
                    return []
            
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(run_discovery)
                available_versions = future.result()
            
            if available_versions:
                # Use the first available version
                best_version = available_versions[0]
                if "npmmirror.com" in base_url:
                    return f"https://registry.npmmirror.com/-/binary/chrome-for-testing/{best_version}/{platform_key}/chromedriver-{platform_key}.zip"
                elif "storage.googleapis.com" in base_url:
                    return f"{base_url}{best_version}/{platform_key}/chromedriver-{platform_key}.zip"
                else:
                    return f"{base_url}{best_version}/chromedriver_{platform_key}.zip"
        
        except Exception as e:
            logger.warning(f"daymic found version failed, use default version: {e}")
        
        # Fallback to current version
        return current_url
