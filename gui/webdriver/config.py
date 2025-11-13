#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WebDriver configuration settings
"""

import os
import platform
import sys
from utils.logger_helper import logger_helper as logger


# Official JSON endpoint for Chrome for Testing versions
KNOWN_GOOD_VERSIONS_URL = "https://googlechromelabs.github.io/chrome-for-testing/known-good-versions-with-downloads.json"

# Fallback JSON endpoint from npmmirror
KNOWN_GOOD_VERSIONS_URL_FALLBACK = "https://registry.npmmirror.com/-/binary/chrome-for-testing/"

# SSL Configuration
SSL_VERIFY = False  # Set to False to skip SSL certificate verification
SSL_CHECK_HOSTNAME = False  # Set to False to skip hostname verification

# Platform mapping for webdriver downloads
PLATFORM_MAP = {
    "win32": "win64",
    "linux": "linux64",
    "darwin": "mac-arm64" if platform.machine() == "arm64" else "mac-x64"
}

# Default Chrome version if detection fails
DEFAULT_CHROME_VERSION = "131.0.6778.85"

# Chrome installation paths by platform
CHROME_PATHS = {
    "Windows": [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
        # Additional paths for custom Chrome installations
        r"C:\Program Files (x86)\Qoom\Chrome\chrome.exe",
        r"C:\Program Files\Qoom\Chrome\chrome.exe",
        # Edge as Chrome alternative
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        # Portable Chrome locations
        os.path.expanduser(r"~\Desktop\Chrome\chrome.exe"),
        os.path.expanduser(r"~\Downloads\Chrome\chrome.exe"),
    ],
    "Darwin": [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        # Additional common macOS Chrome locations
        os.path.expanduser("~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        os.path.expanduser("~/Applications/Chromium.app/Contents/MacOS/Chromium"),
        os.path.expanduser("~/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
    ],
    "Linux": [
        "google-chrome"
    ]
}

# WebDriver file names by platform
WEBDRIVER_NAMES = {
    "Windows": "chromedriver.exe",
    "Darwin": "chromedriver",
    "Linux": "chromedriver"
}

def get_webdriver_dir() -> str:
    """Get webdriver storage directory using app_info paths"""
    try:
        from config.app_info import app_info

        # Use app_info.appdata_path (user-writable) for consistent path management
        # This avoids permission issues when the app is installed under /Applications
        base_dir = os.path.join(app_info.appdata_path, "webdrivers")

        # Ensure directory exists
        os.makedirs(base_dir, exist_ok=True)

        return base_dir

    except ImportError as e:
        logger.error("get webdriver dir failed", str(e))
        return None

def get_cache_dir() -> str:
    """Get cache directory for WebDriver files"""
    webdriver_dir = get_webdriver_dir()
    cache_dir = os.path.join(webdriver_dir, "cache")
    os.makedirs(cache_dir, exist_ok=True)
    return cache_dir

def get_metadata_file() -> str:
    """Get metadata file path for caching information"""
    cache_dir = get_cache_dir()
    return os.path.join(cache_dir, "metadata.json")

def get_temp_dir() -> str:
    """Get temporary directory for WebDriver downloads"""
    try:
        from config.app_info import app_info
        # Use app_info.appdata_temp_path for temporary files
        temp_dir = os.path.join(app_info.appdata_temp_path, "webdriver_downloads")
        os.makedirs(temp_dir, exist_ok=True)
        return temp_dir
    except ImportError:
        # Fallback to system temp directory
        import tempfile
        temp_dir = os.path.join(tempfile.gettempdir(), "eCan_webdriver_downloads")
        os.makedirs(temp_dir, exist_ok=True)
        return temp_dir

def get_log_dir() -> str:
    """Get log directory for WebDriver operations"""
    try:
        from config.app_info import app_info
        # Use app_info.appdata_path for logs
        log_dir = os.path.join(app_info.appdata_path, "logs", "webdriver")
        os.makedirs(log_dir, exist_ok=True)
        return log_dir
    except ImportError:
        # Fallback
        webdriver_dir = get_webdriver_dir()
        log_dir = os.path.join(webdriver_dir, "logs")
        os.makedirs(log_dir, exist_ok=True)
        return log_dir

def get_current_platform() -> str:
    """Get current platform identifier"""
    return PLATFORM_MAP.get(sys.platform, "win64")

def get_webdriver_name() -> str:
    """Get webdriver executable name for current platform"""
    system = platform.system()
    return WEBDRIVER_NAMES.get(system, "chromedriver")

def get_chrome_paths() -> list:
    """Get Chrome installation paths for current platform"""
    system = platform.system()
    return CHROME_PATHS.get(system, [])
