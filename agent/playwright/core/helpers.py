#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Playwright 简化辅助函数
提供最基本的错误处理、首次安装检测和用户友好提示
"""

import os
import sys
import subprocess
from pathlib import Path
from typing import Optional

from utils.logger_helper import logger_helper as logger


def friendly_error_message(exception: Exception, context: str = "") -> str:
    """将技术错误转换为用户友好的消息"""
    error_str = str(exception).lower()

    # 简化的错误匹配
    error_types = {
        ("not found", "no such file", "missing"): "❌ Playwright 浏览器未安装\n💡 运行 auto_install_playwright() 安装",
        ("permission", "access denied", "forbidden"): "❌ 权限不足\n💡 以管理员身份运行",
        ("network", "connection", "timeout", "download"): "❌ 网络问题\n💡 检查网络连接",
        ("disk", "space", "storage"): "❌ 磁盘空间不足\n💡 清理磁盘空间（需要500MB）"
    }

    for keywords, message in error_types.items():
        if any(keyword in error_str for keyword in keywords):
            return message

    return f"❌ Playwright 错误: {exception}\n💡 运行 quick_diagnostics() 检查问题"


def is_first_time_use() -> bool:
    """检查是否是首次使用"""
    try:
        from ..manager import get_playwright_manager
        manager = get_playwright_manager()
        return not manager.is_initialized()
    except Exception:
        return True


def _print_install_environment_info(target_path: Path) -> None:
    """打印安装时的环境信息"""
    import platform

    logger.info("📋 Playwright Installation Environment:")
    logger.info(f"  Platform: {platform.system()}")
    logger.info(f"  Target: {target_path}")
    logger.info(f"  Exists: {'Yes' if target_path.exists() else 'No'}")


def auto_install_playwright(target_path: Optional[Path] = None) -> bool:
    """自动安装 Playwright 浏览器"""
    try:
        from .utils import core_utils

        if target_path is None:
            target_path = core_utils.get_app_data_path() / "ms-playwright"

        logger.info(f"🚀 安装 Playwright 到: {target_path}")
        _print_install_environment_info(target_path)

        target_path.mkdir(parents=True, exist_ok=True)

        # 检查并安装 playwright 包
        try:
            subprocess.run([sys.executable, "-m", "pip", "show", "playwright"],
                         check=True, capture_output=True)
        except subprocess.CalledProcessError:
            logger.info("⏳ 安装 Playwright 包...")
            subprocess.run([sys.executable, "-m", "pip", "install", "playwright"], check=True)

        # 安装浏览器
        env = os.environ.copy()
        env[core_utils.ENV_BROWSERS_PATH] = str(target_path)
        env[core_utils.ENV_CACHE_DIR] = str(target_path)

        logger.info("⏳ 下载浏览器文件...")
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"],
                      check=True, env=env)

        core_utils.set_environment_variables(target_path)
        logger.info(f"✅ 安装成功: {target_path}")
        return True

    except Exception as e:
        error_msg = friendly_error_message(e)
        logger.error(error_msg)
        return False


def quick_diagnostics() -> None:
    """快速诊断常见问题"""
    print("\n🔍 Playwright 快速诊断")
    print("-" * 30)

    issues = []

    # 检查 Playwright 状态
    try:
        from .utils import core_utils
        from ..manager import get_playwright_manager

        manager = get_playwright_manager()
        if not manager.is_initialized():
            issues.append("Playwright 未初始化")

        browsers_path = core_utils.get_environment_browsers_path()
        if not browsers_path or not browsers_path.exists():
            issues.append("浏览器文件不存在")

    except Exception as e:
        issues.append(f"检查失败: {e}")

    # 输出结果
    if not issues:
        print("✅ 系统状态正常")
    else:
        print("❌ 发现问题:")
        for issue in issues:
            print(f"  • {issue}")
        print("\n💡 建议: 运行 auto_install_playwright()")

    print("-" * 30)


def smart_init_prompt() -> None:
    """智能初始化提示"""
    if is_first_time_use():
        print("\n🎯 首次使用 Playwright")
        print("💡 运行: auto_install_playwright()")
        print("🔍 诊断: quick_diagnostics()")


def log_with_emoji(level: str, message: str) -> None:
    """普通的日志记录"""
    getattr(logger, level if level in ["error", "warning"] else "info")(message)


# 便捷函数导出
__all__ = [
    'friendly_error_message',
    'is_first_time_use',
    'auto_install_playwright',
    'quick_diagnostics',
    'smart_init_prompt',
    'log_with_emoji'
]
