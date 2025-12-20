"""
Build Information Module

This module provides a unified interface for accessing build information
across development and production environments.

Architecture:
- build_info.py (this file): Core logic, banner templates, utility functions
- build_data.py (generated): Build data injected at build time
- Fallback: Auto-generates default data for local development

Usage:
    from config.build_info import get_banner, get_version_string, BUILD_INFO
    print(get_banner())
"""

import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional


# ============================================================================
# Data Loading with Fallback
# ============================================================================

def _get_git_info() -> Dict[str, str]:
    """Get Git information for local development fallback"""
    try:
        project_root = Path(__file__).parent.parent
        
        commit = subprocess.check_output(
            ['git', 'rev-parse', '--short', 'HEAD'],
            cwd=project_root,
            stderr=subprocess.DEVNULL
        ).decode().strip()
        
        branch = subprocess.check_output(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
            cwd=project_root,
            stderr=subprocess.DEVNULL
        ).decode().strip()
        
        commit_time = subprocess.check_output(
            ['git', 'log', '-1', '--format=%ci'],
            cwd=project_root,
            stderr=subprocess.DEVNULL
        ).decode().strip()
        
        return {
            'commit': commit,
            'branch': branch,
            'commit_time': commit_time
        }
    except Exception:
        return {
            'commit': 'unknown',
            'branch': 'unknown',
            'commit_time': 'unknown'
        }


def _load_build_data() -> Dict[str, Any]:
    """
    Load build data from build_data.py or generate fallback for local development
    
    Returns:
        Dictionary containing all build information
    """
    try:
        # Try to import generated build data
        from config.build_data import BUILD_DATA
        return BUILD_DATA
    except ImportError:
        # Fallback for local development
        git_info = _get_git_info()
        
        # Try to read version from VERSION file
        version_file = Path(__file__).parent.parent / 'VERSION'
        if version_file.exists():
            version = version_file.read_text().strip()
        else:
            version = "0.0.0-dev"
        
        return {
            "version": version,
            "environment": "development",
            "channel": "dev",
            "git_commit": git_info['commit'],
            "git_branch": git_info['branch'],
            "git_commit_time": git_info['commit_time'],
            "build_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "build_timestamp": datetime.now().timestamp(),
            "ota_enabled": True,
            "signature_required": False,
            "is_fallback": True  # Flag to indicate this is fallback data
        }


# Load build data (with fallback)
_BUILD_DATA = _load_build_data()


# ============================================================================
# Exported Constants
# ============================================================================

VERSION = _BUILD_DATA["version"]
ENVIRONMENT = _BUILD_DATA["environment"]
CHANNEL = _BUILD_DATA["channel"]
GIT_COMMIT = _BUILD_DATA["git_commit"]
GIT_BRANCH = _BUILD_DATA["git_branch"]
GIT_COMMIT_TIME = _BUILD_DATA["git_commit_time"]
BUILD_TIME = _BUILD_DATA["build_time"]
BUILD_TIMESTAMP = _BUILD_DATA["build_timestamp"]
OTA_ENABLED = _BUILD_DATA["ota_enabled"]
SIGNATURE_REQUIRED = _BUILD_DATA["signature_required"]
IS_FALLBACK = _BUILD_DATA.get("is_fallback", False)


# ============================================================================
# Utility Functions
# ============================================================================

def get_version_string() -> str:
    """
    Get full version string with environment suffix
    
    Returns:
        Formatted version string
        - production: "1.0.0"
        - development: "1.0.0-dev-abc123"
        - other: "1.0.0-staging"
    """
    if ENVIRONMENT == "production":
        return VERSION
    elif ENVIRONMENT == "development":
        return f"{VERSION}-dev-{GIT_COMMIT}"
    else:
        return f"{VERSION}-{ENVIRONMENT}"


def get_banner() -> str:
    """
    Get application banner with build information
    
    Returns:
        Formatted banner string for display
    """
    return f"""
╔═══════════════════════════════════════════════════════════╗
║                      eCan.ai                              ║
║                                                           ║
║  Version:     {VERSION:<40} ║
║  Environment: {ENVIRONMENT:<40} ║
║  Channel:     {CHANNEL:<40} ║
║  Build Time:  {BUILD_TIME:<40} ║
║  Git Commit:  {GIT_COMMIT:<40} ║
╚═══════════════════════════════════════════════════════════╝
    """.strip()


def get_short_banner() -> str:
    """
    Get short banner for logging
    
    Returns:
        Compact version string for logs
    """
    return f"eCan.ai v{get_version_string()} [{ENVIRONMENT}] ({GIT_COMMIT})"


def get_startup_banner() -> str:
    """
    Get complete startup banner with system information
    
    Returns:
        Formatted startup banner with build info and system details
    """
    import platform as _platform
    import sys
    from datetime import datetime
    
    # System information
    platform_name = _platform.system()
    platform_release = _platform.release()
    python_version = _platform.python_version()
    is_frozen = getattr(sys, 'frozen', False)
    build_mode = 'Production' if is_frozen else 'Development'
    startup_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    platform_info = f"{platform_name} {platform_release}"
    
    # Build complete startup banner
    # Note: No special marking for fallback - it's the normal development default
    banner = f"""
╔═══════════════════════════════════════════════════════════════════════════════╗
║                                   eCan.AI                                     ║
║                                                                               ║
║  Version:      {get_version_string():<60} ║
║  Environment:  {ENVIRONMENT:<60} ║
║  Channel:      {CHANNEL:<60} ║
║  Git Commit:   {GIT_COMMIT:<60} ║
╠═══════════════════════════════════════════════════════════════════════════════╣
║  Platform:     {platform_info:<60} ║
║  Python:       {python_version:<60} ║
║  Build Mode:   {build_mode:<60} ║
║  Build Time:   {BUILD_TIME:<60} ║
║  Startup Time: {startup_time:<60} ║
╚═══════════════════════════════════════════════════════════════════════════════╝
    """.strip()
    
    return banner


def is_production() -> bool:
    """Check if running in production environment"""
    return ENVIRONMENT == "production"


def is_development() -> bool:
    """Check if running in development environment"""
    return ENVIRONMENT == "development"


def is_staging() -> bool:
    """Check if running in staging environment"""
    return ENVIRONMENT == "staging"


def is_test() -> bool:
    """Check if running in test environment"""
    return ENVIRONMENT == "test"


# ============================================================================
# Complete Build Information Dictionary
# ============================================================================

BUILD_INFO: Dict[str, Any] = {
    "version": VERSION,
    "environment": ENVIRONMENT,
    "channel": CHANNEL,
    "git_commit": GIT_COMMIT,
    "git_branch": GIT_BRANCH,
    "git_commit_time": GIT_COMMIT_TIME,
    "build_time": BUILD_TIME,
    "build_timestamp": BUILD_TIMESTAMP,
    "ota_enabled": OTA_ENABLED,
    "signature_required": SIGNATURE_REQUIRED,
    "is_fallback": IS_FALLBACK,
    "version_string": get_version_string(),
}


# ============================================================================
# Module Initialization
# ============================================================================

# Note: IS_FALLBACK flag is available for callers to check if using fallback data
# Callers can decide whether to show warnings or not
