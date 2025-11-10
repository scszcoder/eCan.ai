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

    # Try Windows App Paths registry for chrome.exe location (prefer file version, avoid launching)
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
                            # First try file version via win32api to avoid spawning a process
                            try:
                                import win32api  # type: ignore
                                info = win32api.GetFileVersionInfo(chrome_exe_path, "\\")
                                ms = info['FileVersionMS']; ls = info['FileVersionLS']
                                version = f"{win32api.HIWORD(ms)}.{win32api.LOWORD(ms)}.{win32api.HIWORD(ls)}.{win32api.LOWORD(ls)}"
                                if re.match(r"\d+\.\d+\.\d+\.\d+", version):
                                    logger.info(f"Detected Chrome version {version} from file properties (App Paths): {chrome_exe_path}")
                                    return version
                            except Exception:
                                # As a last resort, run with --version (still headless)
                                try:
                                    version_output = subprocess.check_output([chrome_exe_path, "--headless", "--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage", "--version"], 
                                                                           stderr=subprocess.STDOUT, text=True, 
                                                                           encoding='utf-8', errors='ignore', timeout=10)
                                    match = re.search(r"(\d+\.\d+\.\d+\.\d+)", version_output)
                                    if match:
                                        version = match.group(1)
                                        logger.info(f"Detected Chrome version {version} from App Paths: {chrome_exe_path}")
                                        return version
                                except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
                                    continue
                except (FileNotFoundError, OSError):
                    continue
        except ImportError:
            pass

    # Windows-specific: Try to get version from known paths via file properties before launching
    if system == "Windows":
        try:
            import win32api  # type: ignore
            chrome_paths = get_chrome_paths()
            for path in chrome_paths:
                if os.path.exists(path):
                    try:
                        info = win32api.GetFileVersionInfo(path, "\\")
                        ms = info['FileVersionMS']; ls = info['FileVersionLS']
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
                        # Use encoding='utf-8' and errors='ignore' to handle encoding issues on Windows
                        version_output = subprocess.check_output([path, "--headless", "--disable-gpu", "--version"], 
                                                               stderr=subprocess.STDOUT, text=True, 
                                                               encoding='utf-8', errors='ignore', timeout=5)
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
                    # Use encoding='utf-8' and errors='ignore' to handle encoding issues on Windows
                    version_output = subprocess.check_output([cmd, "--headless", "--disable-gpu", "--version"], 
                                                           stderr=subprocess.STDOUT, text=True, 
                                                           encoding='utf-8', errors='ignore', timeout=5)
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
                        # Use encoding='utf-8' and errors='ignore' to handle encoding issues on Windows
                        version_output = subprocess.check_output([path, "--headless", "--disable-gpu", "--version"], 
                                                               stderr=subprocess.STDOUT, text=True, 
                                                               encoding='utf-8', errors='ignore', timeout=5)
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
                    # Use encoding='utf-8' and errors='ignore' to handle encoding issues on Windows
                    version_output = subprocess.check_output([cmd, "--headless", "--disable-gpu", "--version"], 
                                                           stderr=subprocess.STDOUT, text=True, 
                                                           encoding='utf-8', errors='ignore', timeout=5)
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

def detect_webdriver_version(webdriver_path: str) -> Optional[str]:
    """Detect the version of an existing webdriver executable"""
    try:
        if not os.path.exists(webdriver_path):
            return None
            
        if not os.access(webdriver_path, os.X_OK):
            return None
            
        # Try to get version using --version flag
        try:
            # Use encoding='utf-8' and errors='ignore' to handle encoding issues on Windows
            version_output = subprocess.check_output([webdriver_path, "--version"], 
                                                   stderr=subprocess.STDOUT, text=True, 
                                                   encoding='utf-8', errors='ignore', timeout=10)
            
            # Parse version from output
            # ChromeDriver output format: "ChromeDriver 120.0.6099.109 (a9f0a9632c)"
            version_match = re.search(r"ChromeDriver\s+(\d+\.\d+\.\d+\.\d+)", version_output)
            if version_match:
                version = version_match.group(1)
                logger.info(f"Detected WebDriver version {version} from: {webdriver_path}")
                return version
                
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
            pass
            
        # Fallback: try to extract version from filename if it follows naming convention
        # Example: chromedriver-120.0.6099.109.exe
        filename = os.path.basename(webdriver_path)
        filename_version_match = re.search(r"chromedriver[_-](\d+\.\d+\.\d+\.\d+)", filename)
        if filename_version_match:
            version = filename_version_match.group(1)
            logger.info(f"Extracted WebDriver version {version} from filename: {filename}")
            return version
            
        return None
        
    except Exception as e:
        logger.error(f"Error detecting WebDriver version: {e}")
        return None

def is_webdriver_compatible(webdriver_path: str, chrome_version: str) -> bool:
    """
    Check if the existing webdriver is compatible with the Chrome version.
    
    Args:
        webdriver_path: Path to the webdriver executable
        chrome_version: Chrome browser version string (e.g., "120.0.6099.109")
        
    Returns:
        bool: True if compatible, False otherwise
    """
    try:
        if not chrome_version:
            logger.warning("Chrome version not provided, cannot check compatibility")
            return False
            
        # Get webdriver version
        webdriver_version = detect_webdriver_version(webdriver_path)
        if not webdriver_version:
            logger.warning(f"Could not detect WebDriver version from: {webdriver_path}")
            return False
            
        # Extract major versions for comparison
        chrome_major = get_chrome_major_version(chrome_version)
        webdriver_major = get_chrome_major_version(webdriver_version)
        
        logger.info(f"Chrome major version: {chrome_major}, WebDriver major version: {webdriver_major}")
        
        # Check if major versions match (Chrome and ChromeDriver major versions should match)
        if chrome_major == webdriver_major:
            logger.info(f"✅ WebDriver version {webdriver_version} is compatible with Chrome version {chrome_version}")
            return True
        else:
            logger.warning(f"❌ WebDriver version {webdriver_version} (major: {webdriver_major}) is NOT compatible with Chrome version {chrome_version} (major: {chrome_major})")
            return False
            
    except Exception as e:
        logger.error(f"Error checking WebDriver compatibility: {e}")
        return False
        
    except Exception as e:
        logger.error(f"Error checking WebDriver compatibility: {e}")
        return False

def find_compatible_webdriver(webdriver_dir: str, chrome_version: str) -> Optional[str]:
    """
    Find an existing webdriver that is compatible with the specified Chrome version.
    
    Args:
        webdriver_dir: Directory to search for webdrivers
        chrome_version: Chrome browser version string
        
    Returns:
        Optional[str]: Path to compatible webdriver, or None if not found
    """
    try:
        if not os.path.exists(webdriver_dir):
            return None
            
        system = platform.system()
        driver_name = "chromedriver.exe" if system == "Windows" else "chromedriver"
        
        # Search for webdrivers recursively
        compatible_drivers = []
        
        for root, _, files in os.walk(webdriver_dir):
            if driver_name in files:
                driver_path = os.path.join(root, driver_name)
                if os.path.exists(driver_path) and os.access(driver_path, os.X_OK):
                    # Check compatibility
                    if is_webdriver_compatible(driver_path, chrome_version):
                        compatible_drivers.append(driver_path)
                        
        if compatible_drivers:
            # Return the first compatible driver found
            # You could implement more sophisticated selection logic here
            # (e.g., prefer newer versions, prefer specific locations, etc.)
            selected_driver = compatible_drivers[0]
            logger.info(f"Found {len(compatible_drivers)} compatible WebDriver(s), using: {selected_driver}")
            return selected_driver
            
        logger.info(f"No compatible WebDriver found for Chrome version {chrome_version}")
        return None
        
    except Exception as e:
        logger.error(f"Error finding compatible WebDriver: {e}")
        return None

def should_download_webdriver(webdriver_dir: str, chrome_version: str) -> tuple[bool, Optional[str]]:
    """
    Determine if a webdriver download is needed.
    
    Args:
        webdriver_dir: Directory to search for existing webdrivers
        chrome_version: Chrome browser version string
        
    Returns:
        tuple[bool, Optional[str]]: (needs_download, existing_driver_path)
            - needs_download: True if download is needed, False if compatible driver exists
            - existing_driver_path: Path to existing compatible driver, or None
    """
    try:
        # First, try to find a compatible existing webdriver
        existing_driver = find_compatible_webdriver(webdriver_dir, chrome_version)
        
        if existing_driver:
            logger.info(f"✅ Compatible WebDriver found: {existing_driver}")
            return False, existing_driver
        else:
            logger.info(f"❌ No compatible WebDriver found for Chrome version {chrome_version}")
            return True, None
            
    except Exception as e:
        logger.error(f"Error determining if WebDriver download is needed: {e}")
        # If there's an error, assume we need to download
        return True, None

def check_webdriver_status_example():
    """
    Example function showing how to use the new WebDriver version detection functions.
    This demonstrates the complete workflow for checking if a download is needed.
    """
    try:
        from .config import get_webdriver_dir
        
        # Get the webdriver directory
        webdriver_dir = get_webdriver_dir()
        if not webdriver_dir:
            logger.error("Could not determine webdriver directory")
            return None, None
            
        # Detect Chrome version
        chrome_version = detect_chrome_version()
        logger.info(f"Detected Chrome version: {chrome_version}")
        
        # Check if we need to download a new webdriver
        needs_download, existing_driver = should_download_webdriver(webdriver_dir, chrome_version)
        
        if needs_download:
            logger.info("🔄 WebDriver download is needed")
            return None, chrome_version
        else:
            logger.info("✅ Compatible WebDriver already exists")
            return existing_driver, chrome_version
            
    except Exception as e:
        logger.error(f"Error in webdriver status check: {e}")
        return None, None
