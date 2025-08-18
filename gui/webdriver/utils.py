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

def detect_chrome_version() -> str:
    """Detect Chrome browser version"""
    try:
        system = platform.system()
        chrome_paths = get_chrome_paths()
        
        for path in chrome_paths:
            if os.path.exists(path):
                try:
                    version = subprocess.check_output([path, "--version"], 
                                                   stderr=subprocess.STDOUT, 
                                                   text=True)
                    
                    # Extract version number
                    if system == "Windows":
                        match = re.search(r"Chrome\s+(\d+\.\d+\.\d+\.\d+)", version)
                    elif system == "Darwin":
                        match = re.search(r"Chrome\s+(\d+\.\d+\.\d+\.\d+)", version)
                    else:  # Linux
                        match = re.search(r"Google Chrome\s+(\d+\.\d+\.\d+\.\d+)", version)
                    
                    if match:
                        return match.group(1)
                        
                except (subprocess.CalledProcessError, FileNotFoundError):
                    continue
        
        return DEFAULT_CHROME_VERSION
        
    except Exception:
        return DEFAULT_CHROME_VERSION

def find_existing_webdriver(webdriver_dir: str) -> Optional[str]:
    """Find existing webdriver in the specified directory (recursive search)"""
    try:
        if not os.path.exists(webdriver_dir):
            return None
            
        system = platform.system()
        driver_name = "chromedriver.exe" if system == "Windows" else "chromedriver"
        
        # Recursive search for chromedriver
        for root, dirs, files in os.walk(webdriver_dir):
            if driver_name in files:
                driver_path = os.path.join(root, driver_name)
                if os.path.exists(driver_path) and os.access(driver_path, os.X_OK):
                    return driver_path
        
        return None
        
    except Exception:
        return None

def find_project_webdriver() -> Optional[str]:
    """Find webdriver in project directory"""
    try:
        from .config import PROJECT_WEBDRIVER_PATHS
        
        for driver_path in PROJECT_WEBDRIVER_PATHS:
            full_path = os.path.join(os.getcwd(), driver_path)
            if os.path.exists(full_path) and os.access(full_path, os.X_OK):
                return full_path
        
        return None
        
    except Exception:
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
        
    except Exception:
        return False

def get_chrome_major_version(version: str) -> str:
    """Extract major version number from Chrome version string"""
    try:
        return version.split('.')[0]
    except (IndexError, AttributeError):
        return "120"  # Default major version
