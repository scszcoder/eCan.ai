#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WebDriver utility functions
"""

import os
import platform
import re
import subprocess
from typing import Optional, List

from .config import CHROME_PATHS, DEFAULT_CHROME_VERSION, get_chrome_paths

from utils.logger_helper import logger_helper as logger

def detect_chrome_version() -> str:
    """Detect Chrome browser version with platform-specific strategies."""
    system = platform.system()

    # Windows: Prioritize registry query, fallback to file path check.
    if system == "Windows":
        try:
            import winreg
            # Query the registry for Chrome's version
            key_path = r"SOFTWARE\Google\Chrome\BLBeacon"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                version, _ = winreg.QueryValueEx(key, "version")
                if version:
                    logger.info(f"Detected Chrome version {version} from registry.")
                    return version
        except (ImportError, FileNotFoundError, OSError):
            logger.warning("Could not query registry for Chrome version. Falling back to file path check.")
            pass # Fallback to the file check method below

    # Fallback for Windows and primary method for other OS
    try:
        chrome_paths = get_chrome_paths()
        for path in chrome_paths:
            if os.path.exists(path):
                try:
                    command = [path, "--version"]
                    version_output = subprocess.check_output(command, stderr=subprocess.STDOUT, text=True)

                    # Regex patterns for different OS
                    patterns = {
                        "Windows": r"Chrome\s+(\d+\.\d+\.\d+\.\d+)",
                        "Darwin": r"Chrome\s+(\d+\.\d+\.\d+\.\d+)",
                        "Linux": r"Google Chrome\s+(\d+\.\d+\.\d+\.\d+)"
                    }
                    match = re.search(patterns.get(system, ""), version_output)
                    if match:
                        logger.info(f"Detected Chrome version {match.group(1)} from path: {path}")
                        return match.group(1)
                except (subprocess.CalledProcessError, FileNotFoundError):
                    continue
    except Exception as e:
        logger.error(f"Error detecting Chrome version from file paths: {e}")

    logger.warning(f"Could not detect Chrome version. Falling back to default: {DEFAULT_CHROME_VERSION}")
    return DEFAULT_CHROME_VERSION

def find_existing_webdriver(webdriver_dir: str) -> Optional[str]:
    """Find existing webdriver in the specified directory (recursive search)"""
    try:
        if not os.path.exists(webdriver_dir):
            return None

        system = platform.system()
        driver_name = "chromedriver.exe" if system == "Windows" else "chromedriver"

        # Recursive search for chromedriver
        for root, _, files in os.walk(webdriver_dir):
            if driver_name in files:
                driver_path = os.path.join(root, driver_name)
                if os.path.exists(driver_path) and os.access(driver_path, os.X_OK):
                    return driver_path

        return None

    except Exception as e:
        logger.error("find existing webdriver error", str(e))
        return None

def is_webdriver_executable(file_path: str) -> bool:
    """Check if file is an executable webdriver"""
    try:
        if not os.path.exists(file_path):
            return False

        # Check if file is executable
        if not os.access(file_path, os.X_OK):
            return False

        # Check file name
        filename = os.path.basename(file_path)
        return filename in ["chromedriver", "chromedriver.exe"]

    except Exception as e:
        logger.error("is webdriver executable error", str(e))
        return False

def get_chrome_major_version(version: str) -> str:
    """Extract major version number from Chrome version string"""
    try:
        return version.split('.')[0]
    except (IndexError, AttributeError):
        return "120"  # Default major version
