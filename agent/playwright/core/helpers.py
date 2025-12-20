#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Playwright Simplified Helper Functions
Provides basic error handling, first-time installation detection and user-friendly prompts
"""

import os
import sys
import subprocess
from pathlib import Path
from typing import Optional

from utils.logger_helper import logger_helper as logger


def friendly_error_message(exception: Exception, context: str = "") -> str:
    """Convert technical errors to user-friendly messages"""
    error_str = str(exception).lower()

    # Simplified error matching
    error_types = {
        ("not found", "no such file", "missing"): "❌ Playwright browsers not installed\n💡 Run auto_install_playwright() to install",
        ("permission", "access denied", "forbidden"): "❌ Insufficient permissions\n💡 Run as administrator",
        ("network", "connection", "timeout", "download"): "❌ Network issues\n💡 Check network connection",
        ("disk", "space", "storage"): "❌ Insufficient disk space\n💡 Free up disk space (500MB required)"
    }

    for keywords, message in error_types.items():
        if any(keyword in error_str for keyword in keywords):
            return message

    return f"❌ Playwright error: {exception}\n💡 Run quick_diagnostics() to check issues"


def is_first_time_use() -> bool:
    """Check if this is first-time use"""
    try:
        from ..manager import get_playwright_manager
        manager = get_playwright_manager()
        return not manager.is_initialized()
    except Exception:
        return True


def _print_install_environment_info(target_path: Path) -> None:
    """Print environment information during installation"""
    import platform

    logger.info("📋 Playwright Installation Environment:")
    logger.info(f"  Platform: {platform.system()}")
    logger.info(f"  Target: {target_path}")
    logger.info(f"  Exists: {'Yes' if target_path.exists() else 'No'}")


def auto_install_playwright(target_path: Optional[Path] = None) -> bool:
    """Automatically install Playwright browsers"""
    try:
        from .utils import core_utils

        if target_path is None:
            target_path = core_utils.get_app_data_path() / "ms-playwright"

        _print_install_environment_info(target_path)

        target_path.mkdir(parents=True, exist_ok=True)

        # Check and install playwright package
        from utils.subprocess_helper import run_no_window
        try:
            run_no_window([sys.executable, "-m", "pip", "show", "playwright"],
                         check=True, capture_output=True)
        except subprocess.CalledProcessError:
            logger.info("⏳ Installing Playwright package...")
            run_no_window([sys.executable, "-m", "pip", "install", "playwright"], check=True)

        # Install browsers
        env = os.environ.copy()
        env[core_utils.ENV_BASE_DIR] = str(target_path)
        env[core_utils.ENV_CACHE_DIR] = str(target_path)

        logger.info("⏳ Downloading browser files...")
        run_no_window([sys.executable, "-m", "playwright", "install", "chromium"],
                      check=True, env=env)

        core_utils.set_environment_variables(target_path)
        logger.info(f"✅ Installation successful: {target_path}")
        return True
    except Exception as e:
        error_msg = friendly_error_message(e)
        logger.error(error_msg)
        return False


def quick_diagnostics() -> None:
    """Quick diagnosis of common issues"""
    print("\n🔍 Playwright Quick Diagnosis")
    print("-" * 30)

    issues = []

    # Check Playwright status
    try:
        from .utils import core_utils
        from ..manager import get_playwright_manager

        manager = get_playwright_manager()
        if not manager.is_initialized():
            issues.append("Playwright not initialized")

        browsers_path = core_utils.get_environment_browsers_path()
        if not browsers_path or not browsers_path.exists():
            issues.append("Browser files do not exist")

    except Exception as e:
        issues.append(f"check failed: {e}")

    # output results
    if not issues:
        print("[OK] System status normal")
    else:
        print("[ERROR] Issues found:")
        for issue in issues:
            print(f"  • {issue}")
        print("\n💡 suggestions: Run auto_install_playwright()")

    print("-" * 30)


def smart_init_prompt() -> None:
    """Smart initialization prompt"""
    if is_first_time_use():
        print("\n🎯 First time using Playwright")
        print("💡 Run: auto_install_playwright()")
        print("🔍 Diagnose: quick_diagnostics()")


def log_with_emoji(level: str, message: str) -> None:
    """Simple logging"""
    getattr(logger, level if level in ["error", "warning"] else "info")(message)


# Convenience functions export
__all__ = [
    'friendly_error_message',
    'is_first_time_use',
    'auto_install_playwright',
    'quick_diagnostics',
    'smart_init_prompt',
    'log_with_emoji'
]
