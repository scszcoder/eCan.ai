#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Playwright 核心工具模块
提供 Playwright 的基础工具函数，包括路径处理、安装、验证等
"""

import os
import sys
import shutil
import subprocess
import platform
from pathlib import Path
from typing import Optional, List
from utils.logger_helper import logger_helper as logger

# 导入简化的辅助函数
try:
    from .helpers import friendly_error_message
except ImportError:
    # 向后兼容，如果新模块不可用
    def friendly_error_message(exception, context=""):
        return str(exception)


class PlaywrightCoreUtils:
    """Playwright 核心工具类"""
    
    # 浏览器类型
    BROWSER_TYPE = "chromium"
    
    # 环境变量名称
    ENV_BROWSERS_PATH = "PLAYWRIGHT_BROWSERS_PATH"
    ENV_CACHE_DIR = "PLAYWRIGHT_CACHE_DIR"
    ENV_BROWSERS_PATH_OVERRIDE = "PLAYWRIGHT_BROWSERS_PATH_OVERRIDE"
    
    # 应用名称
    APP_NAME = "eCan"
    
    @staticmethod
    def get_default_browsers_path() -> Path:
        """获取默认的浏览器安装路径"""
        if sys.platform == "darwin":  # macOS
            return Path.home() / ".cache" / "ms-playwright"
        elif sys.platform == "win32":  # Windows
            return Path.home() / "AppData" / "Local" / "ms-playwright"
        else:  # Linux
            return Path.home() / ".cache" / "ms-playwright"
    
    @staticmethod
    def get_app_data_path() -> Path:
        """获取应用数据目录"""
        if sys.platform == "darwin":  # macOS
            return Path.home() / "Library" / "Application Support" / PlaywrightCoreUtils.APP_NAME
        elif sys.platform == "win32":  # Windows
            return Path.home() / "AppData" / "Local" / PlaywrightCoreUtils.APP_NAME
        else:  # Linux
            return Path.home() / ".local" / "share" / PlaywrightCoreUtils.APP_NAME
    
    @staticmethod
    def get_bundled_path() -> Optional[Path]:
        """获取打包后的浏览器路径（如果在 PyInstaller 环境中）"""
        if getattr(sys, 'frozen', False):
            return Path(sys._MEIPASS) / "third_party" / "ms-playwright"
        return None
    
    @staticmethod
    def get_possible_cache_paths() -> List[Path]:
        """获取所有可能的缓存路径"""
        possible_roots = []
        
        if platform.system() == "Windows":
            possible_roots.extend([
                Path(os.getenv("LOCALAPPDATA", "")) / "ms-playwright",
                Path.home() / "AppData" / "Local" / "ms-playwright",
                Path.home() / "AppData" / "Roaming" / "ms-playwright"
            ])
        elif platform.system() == "Darwin":  # macOS
            possible_roots.extend([
                Path.home() / ".cache" / "ms-playwright",
                Path.home() / "Library" / "Caches" / "ms-playwright",
                Path.home() / "Library" / "Application Support" / "ms-playwright"
            ])
        else:  # Linux and others
            possible_roots.extend([
                Path.home() / ".cache" / "ms-playwright",
                Path.home() / ".local" / "share" / "ms-playwright",
                Path.home() / ".ms-playwright"
            ])
        
        # 也检查当前工作目录
        possible_roots.append(Path.cwd() / ".ms-playwright")
        
        return possible_roots
    
    @staticmethod
    def validate_browser_installation(path: Path) -> bool:
        """验证浏览器安装是否有效"""
        logger.info(f"开始验证安装: {path}")

        if not path or not path.exists():
            logger.error(f"安装验证失败: {path} - 路径不存在")
            return False

        # 检查关键文件 - 更实用的验证方法
        try:
            # 方法1：检查 browsers.json 文件（推荐但不强制）
            browsers_json = path / "browsers.json"
            if browsers_json.exists():
                try:
                    import json
                    with open(browsers_json, 'r') as f:
                        browsers_data = json.load(f)
                    if isinstance(browsers_data, dict):
                        logger.info(f"找到有效的 browsers.json: {path}")
                        return True
                    else:
                        logger.warning(f"browsers.json 格式无效，尝试其他验证方法")
                except Exception as e:
                    logger.warning(f"browsers.json 读取失败: {e}，尝试其他验证方法")
            else:
                logger.info(f"未找到 browsers.json，使用目录检查方法")

            # 方法2：检查浏览器目录
            chromium_dirs = list(path.glob("chromium*"))
            firefox_dirs = list(path.glob("firefox*"))
            webkit_dirs = list(path.glob("webkit*"))

            all_browser_dirs = chromium_dirs + firefox_dirs + webkit_dirs

            if not all_browser_dirs:
                # 检查是否有其他可能的浏览器目录
                browser_dirs = [d for d in path.iterdir()
                              if d.is_dir() and not d.name.startswith('.') and
                              any(browser in d.name.lower() for browser in ['chrome', 'firefox', 'safari', 'edge'])]
                if not browser_dirs:
                    logger.error(f"安装验证失败: {path} - 未找到任何浏览器目录")
                    return False
                all_browser_dirs = browser_dirs

            logger.info(f"找到浏览器目录: {[d.name for d in all_browser_dirs]}")

            # 检查目录是否包含实际文件（不是空目录）
            valid_browser_found = False
            for browser_dir in all_browser_dirs:
                if browser_dir.is_dir():
                    files = list(browser_dir.rglob("*"))
                    file_count = len(files)

                    # 更智能的验证逻辑
                    if file_count < 10:
                        logger.warning(f"浏览器目录 {browser_dir.name} 文件较少: {file_count}")
                        # 检查是否有关键的可执行文件
                        executables = [f for f in files if f.is_file() and (
                            f.name.lower().startswith('chrome') or
                            f.name.lower().startswith('chromium') or
                            f.name.lower().startswith('firefox') or
                            f.suffix.lower() in ['.exe', '.app', '']
                        )]
                        if not executables:
                            logger.warning(f"在 {browser_dir.name} 中未找到可执行文件")
                            continue
                        else:
                            logger.info(f"在 {browser_dir.name} 中找到 {len(executables)} 个可执行文件")
                    else:
                        logger.info(f"浏览器目录 {browser_dir.name} 包含 {file_count} 个文件")

                    valid_browser_found = True
                    break

            if not valid_browser_found:
                logger.error(f"安装验证失败: {path} - 未找到有效的浏览器安装")
                return False

            logger.info(f"安装验证成功: {path}")
            return True

        except Exception as e:
            logger.error(f"安装验证失败: {path} - 验证过程出错: {e}")
            return False
    
    @staticmethod
    def find_playwright_cache() -> Optional[Path]:
        """查找 Playwright 缓存目录"""
        possible_roots = PlaywrightCoreUtils.get_possible_cache_paths()
        
        # 首先检查环境变量中设置的路径
        env_path = os.getenv(PlaywrightCoreUtils.ENV_BROWSERS_PATH)
        if env_path:
            env_path_obj = Path(env_path)
            if env_path_obj.exists() and (env_path_obj / "browsers.json").exists():
                return env_path_obj
        
        # 优先检查用户主目录下的缓存
        home_cache = Path.home() / ".cache" / "ms-playwright"
        if home_cache.exists() and (home_cache / "browsers.json").exists():
            return home_cache
        
        # 检查应用数据目录
        app_data_cache = PlaywrightCoreUtils.get_app_data_path() / "ms-playwright"
        if app_data_cache.exists() and (app_data_cache / "browsers.json").exists():
            return app_data_cache
        
        # 然后查找其他可能的路径
        for root in possible_roots:
            if root.exists() and (root / "browsers.json").exists():
                return root
        
        # 如果没有找到 browsers.json，查找包含 chromium 的目录
        for root in possible_roots:
            if root.exists():
                chromium_dirs = list(root.glob("**/chromium*"))
                if chromium_dirs:
                    # 向上查找 ms-playwright 根目录
                    current = chromium_dirs[0].parent
                    while current.parent != current:  # 停止在根目录
                        if current.name == "ms-playwright":
                            return current
                        current = current.parent
        
        # 最后手段：搜索任何 ms-playwright 目录
        search_paths = [Path.home(), Path.cwd()]
        for search_path in search_paths:
            if search_path.exists():
                for found in search_path.rglob("ms-playwright"):
                    if (found / "browsers.json").exists():
                        return found
        
        return None
    
    @staticmethod
    def install_playwright_browsers(target_path: Path) -> None:
        """安装 Playwright 浏览器到指定路径"""
        # 确保 playwright 包已安装
        try:
            subprocess.run([sys.executable, "-m", "pip", "show", "playwright"], 
                         check=True, capture_output=True)
        except subprocess.CalledProcessError:
            logger.error("[PLAYWRIGHT] playwright not found; installing...")
            subprocess.run([sys.executable, "-m", "pip", "install", "playwright"], check=True)
        
        # 设置环境变量用于子进程
        env = os.environ.copy()
        env[PlaywrightCoreUtils.ENV_BROWSERS_PATH] = str(target_path)
        env[PlaywrightCoreUtils.ENV_CACHE_DIR] = str(target_path)
        
        # 安装浏览器 - 安装 chromium 和 chromium-headless-shell
        logger.info("[PLAYWRIGHT] Installing chromium browsers...")
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium", "chromium-headless-shell"],
                      check=True, env=env)
    
    @staticmethod
    def cleanup_incomplete_browsers(path: Path) -> None:
        """清理不完整的浏览器目录"""
        if not path or not path.exists():
            return

        logger.info(f"开始清理不完整的安装: {path}")
        cleaned_count = 0

        try:
            # 查找所有 chromium 目录
            chromium_dirs = list(path.glob("chromium*"))

            for browser_dir in chromium_dirs:
                if browser_dir.is_dir():
                    files = list(browser_dir.rglob("*"))
                    file_count = len(files)

                    # 如果文件数量太少，认为是不完整的安装
                    if file_count < 10:
                        # 检查是否有关键的可执行文件
                        executables = [f for f in files if f.is_file() and (
                            f.name.lower().startswith('chrome') or
                            f.name.lower().startswith('chromium') or
                            f.suffix.lower() in ['.exe', '.app', '']
                        )]

                        if not executables:
                            logger.info(f"[PLAYWRIGHT] Cleaning incomplete browser directory: {browser_dir} ({file_count} files)")
                            try:
                                shutil.rmtree(browser_dir, ignore_errors=True)
                                cleaned_count += 1
                            except Exception as e:
                                logger.warning(f"[PLAYWRIGHT] Failed to clean {browser_dir}: {e}")
                        else:
                            logger.debug(f"[PLAYWRIGHT] Keeping {browser_dir} (has executables)")

            logger.info(f"清理完成: {path} (清理了 {cleaned_count} 个项目)")

        except Exception as e:
            friendly_error_message(e, "cleanup_incomplete_browsers")

    @staticmethod
    def copy_playwright_browsers(src_path: Path, dst_path: Path) -> None:
        """复制 Playwright 浏览器文件"""
        if dst_path.exists():
            logger.warning(f"[PLAYWRIGHT] Cleaning existing {dst_path}")
            shutil.rmtree(dst_path, ignore_errors=True)

        logger.info(f"[PLAYWRIGHT] Copying {src_path} -> {dst_path}")
        shutil.copytree(src_path, dst_path)
        logger.info(f"[PLAYWRIGHT] Successfully copied browsers to {dst_path}")
    

    
    @staticmethod
    def set_environment_variables(browsers_path: Path) -> None:
        """设置 Playwright 环境变量"""
        os.environ[PlaywrightCoreUtils.ENV_BROWSERS_PATH] = str(browsers_path)
        os.environ[PlaywrightCoreUtils.ENV_CACHE_DIR] = str(browsers_path)
        os.environ[PlaywrightCoreUtils.ENV_BROWSERS_PATH_OVERRIDE] = str(browsers_path)
    
    @staticmethod
    def get_environment_browsers_path() -> Optional[Path]:
        """从环境变量获取浏览器路径"""
        env_path = os.getenv(PlaywrightCoreUtils.ENV_BROWSERS_PATH)
        if env_path:
            return Path(env_path)
        return None
    
    @staticmethod
    def clear_environment_variables() -> None:
        """清除 Playwright 环境变量"""
        for env_var in [
            PlaywrightCoreUtils.ENV_BROWSERS_PATH,
            PlaywrightCoreUtils.ENV_CACHE_DIR,
            PlaywrightCoreUtils.ENV_BROWSERS_PATH_OVERRIDE
        ]:
            if env_var in os.environ:
                del os.environ[env_var]


# 全局工具实例
core_utils = PlaywrightCoreUtils()
