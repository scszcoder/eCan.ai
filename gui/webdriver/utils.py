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
            # Try multiple registry locations and hives
            registry_locations = [
                (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Google\Chrome\BLBeacon", "version"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Google\Chrome\BLBeacon", "version"),
                (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Google\Update\Clients\{8A69D345-D564-463C-AFF1-A69D9E530F96}", "pv"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Google\Update\Clients\{8A69D345-D564-463C-AFF1-A69D9E530F96}", "pv"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Google\Update\Clients\{8A69D345-D564-463C-AFF1-A69D9E530F96}", "pv"),
            ]
            
            for hive, key_path, value_name in registry_locations:
                try:
                    with winreg.OpenKey(hive, key_path) as key:
                        version, _ = winreg.QueryValueEx(key, value_name)
                        if version and re.match(r"\d+\.\d+\.\d+\.\d+", str(version)):
                            logger.info(f"Detected Chrome version {version} from registry {key_path}")
                            return str(version)
                except (FileNotFoundError, OSError):
                    continue
                    
        except ImportError:
            logger.warning("winreg module not available. Falling back to file path check.")
            pass # Fallback to the file check method below

    # Try Windows App Paths registry for chrome.exe location
    if system == "Windows":
        try:
            import winreg
            app_paths = [
                (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"),
            ]
            
            for hive, key_path in app_paths:
                try:
                    with winreg.OpenKey(hive, key_path) as key:
                        chrome_exe_path, _ = winreg.QueryValueEx(key, "")  # Default value
                        if chrome_exe_path and os.path.exists(chrome_exe_path):
                            try:
                                # Use multiple flags to prevent browser from opening, especially on Windows
                                version_output = subprocess.check_output([chrome_exe_path, "--headless", "--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage", "--version"], 
                                                                       stderr=subprocess.STDOUT, text=True, timeout=10)
                                match = re.search(r"(\d+\.\d+\.\d+\.\d+)", version_output)
                                if match:
                                    version = match.group(1)
                                    logger.info(f"Detected Chrome version {version} from App Paths: {chrome_exe_path}")
                                    return version
                            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                                continue
                except (FileNotFoundError, OSError):
                    continue
        except ImportError:
            pass

    # Windows-specific: Try to get version from file properties as last resort
    if system == "Windows":
        logger.info("Trying Windows file version detection as final fallback")
        try:
            import win32api
            chrome_paths = get_chrome_paths()
            for path in chrome_paths:
                if os.path.exists(path):
                    try:
                        info = win32api.GetFileVersionInfo(path, "\\")
                        ms = info['FileVersionMS']
                        ls = info['FileVersionLS']
                        version = f"{win32api.HIWORD(ms)}.{win32api.LOWORD(ms)}.{win32api.HIWORD(ls)}.{win32api.LOWORD(ls)}"
                        if re.match(r"\d+\.\d+\.\d+\.\d+", version):
                            logger.info(f"Detected Chrome version {version} from file properties: {path}")
                            return version
                    except Exception:
                        continue
        except ImportError:
            logger.debug("win32api not available for file version detection")
    
    # macOS: Try specific detection methods first
    elif system == "Darwin":
        try:
            # Try configured Chrome paths first (most reliable on macOS)
            chrome_paths = get_chrome_paths()
            for path in chrome_paths:
                if os.path.exists(path):
                    try:
                        # Use --headless and --disable-gpu to prevent browser from opening
                        version_output = subprocess.check_output([path, "--headless", "--disable-gpu", "--version"], 
                                                               stderr=subprocess.STDOUT, text=True, timeout=5)
                        # More flexible regex patterns that handle localized output
                        patterns = [
                            r"Google Chrome\s+(\d+\.\d+\.\d+\.\d+)",  # Standard format
                            r"Chrome\s+(\d+\.\d+\.\d+\.\d+)",        # Short format
                            r"Chromium\s+(\d+\.\d+\.\d+\.\d+)",      # Chromium
                            r"Microsoft Edge\s+(\d+\.\d+\.\d+\.\d+)", # Edge
                            r"(\d+\.\d+\.\d+\.\d+)"                  # Just version numbers
                        ]
                        
                        for pattern in patterns:
                            match = re.search(pattern, version_output)
                            if match:
                                version = match.group(1)
                                logger.info(f"Detected Chrome version {version} from: {path}")
                                return version
                    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
                        continue
            
            # Try PATH commands as fallback
            path_commands = ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser"]
            for cmd in path_commands:
                try:
                    # Use --headless and --disable-gpu to prevent browser from opening
                    version_output = subprocess.check_output([cmd, "--headless", "--disable-gpu", "--version"], 
                                                           stderr=subprocess.STDOUT, text=True, timeout=5)
                    # More flexible regex patterns that handle localized output
                    patterns = [
                        r"Google Chrome\s+(\d+\.\d+\.\d+\.\d+)",  # Standard format
                        r"Chrome\s+(\d+\.\d+\.\d+\.\d+)",        # Short format
                        r"Chromium\s+(\d+\.\d+\.\d+\.\d+)",      # Chromium
                        r"Microsoft Edge\s+(\d+\.\d+\.\d+\.\d+)", # Edge
                        r"(\d+\.\d+\.\d+\.\d+)"                  # Just version numbers
                    ]
                    
                    for pattern in patterns:
                        match = re.search(pattern, version_output)
                        if match:
                            version = match.group(1)
                            logger.info(f"Detected Chrome version {version} from: {cmd}")
                            return version
                except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
                    continue
                    
        except Exception as e:
            logger.error(f"Error detecting Chrome version on macOS: {e}")
    
    # Linux and other platforms: Try PATH commands and configured paths
    else:
        try:
            # Try configured Chrome paths
            chrome_paths = get_chrome_paths()
            for path in chrome_paths:
                if os.path.exists(path):
                    try:
                        # Use --headless and --disable-gpu to prevent browser from opening
                        version_output = subprocess.check_output([path, "--headless", "--disable-gpu", "--version"], 
                                                               stderr=subprocess.STDOUT, text=True, timeout=5)
                        # More flexible regex patterns that handle localized output
                        patterns = [
                            r"Google Chrome\s+(\d+\.\d+\.\d+\.\d+)",  # Standard format
                            r"Chrome\s+(\d+\.\d+\.\d+\.\d+)",        # Short format
                            r"Chromium\s+(\d+\.\d+\.\d+\.\d+)",      # Chromium
                            r"Microsoft Edge\s+(\d+\.\d+\.\d+\.\d+)", # Edge
                            r"(\d+\.\d+\.\d+\.\d+)"                  # Just version numbers
                        ]
                        
                        for pattern in patterns:
                            match = re.search(pattern, version_output)
                            if match:
                                version = match.group(1)
                                logger.info(f"Detected Chrome version {version} from: {path}")
                                return version
                    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
                        continue
            
            # Try PATH commands (works on all platforms)
            path_commands = ["chrome", "google-chrome", "google-chrome-stable", "chromium", "chromium-browser"]
            for cmd in path_commands:
                try:
                    # Use --headless and --disable-gpu to prevent browser from opening
                    version_output = subprocess.check_output([cmd, "--headless", "--disable-gpu", "--version"], 
                                                           stderr=subprocess.STDOUT, text=True, timeout=5)
                    # More flexible regex patterns that handle localized output
                    patterns = [
                        r"Google Chrome\s+(\d+\.\d+\.\d+\.\d+)",  # Standard format
                        r"Chrome\s+(\d+\.\d+\.\d+\.\d+)",        # Short format
                        r"Chromium\s+(\d+\.\d+\.\d+\.\d+)",      # Chromium
                        r"Microsoft Edge\s+(\d+\.\d+\.\d+\.\d+)", # Edge
                        r"(\d+\.\d+\.\d+\.\d+)"                  # Just version numbers
                    ]
                    
                    for pattern in patterns:
                        match = re.search(pattern, version_output)
                        if match:
                            version = match.group(1)
                            logger.info(f"Detected Chrome version {version} from: {cmd}")
                            return version
                except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
                    continue
                    
        except Exception as e:
            logger.error(f"Error detecting Chrome version: {e}")

    # Final fallback: Use a more recent default version
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
