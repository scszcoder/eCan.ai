#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WebDriver configuration settings
"""

import os
import platform
import sys

# Base URLs for Chrome for Testing
CHROME_FOR_TESTING_BASE_URL = "https://registry.npmmirror.com/binary.html?path=chrome-for-testing/"
CHROME_FOR_TESTING_DOWNLOAD_URL = "https://registry.npmmirror.com/binary/chrome-for-testing/"

# Platform mapping for webdriver downloads
PLATFORM_MAP = {
    "win32": "win64",
    "linux": "linux64", 
    "darwin": "mac-x64"
}

# Default Chrome version if detection fails
DEFAULT_CHROME_VERSION = "120.0.6099.109"

# Chrome installation paths by platform
CHROME_PATHS = {
    "Windows": [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe")
    ],
    "Darwin": [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
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

# Project directory webdriver paths
PROJECT_WEBDRIVER_PATHS = [
    "chromedriver-win64/chromedriver.exe",
    "chromedriver-win64/chromedriver",
    "chromedriver-linux64/chromedriver",
    "chromedriver-mac-x64/chromedriver"
]

def get_webdriver_dir() -> str:
    """Get webdriver storage directory"""
    home_path = os.path.expanduser("~")
    ecbot_data_home = os.environ.get("ECBOT_DATA_HOME", f"{home_path}/.ecbot")
    return os.path.join(ecbot_data_home, "webdrivers")

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
