#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Playwright 构建时工具模块
专门用于构建时的 Playwright 资源准备，不包含任何运行时逻辑
"""

import os
import sys
import shutil
import subprocess
import platform
from pathlib import Path
from typing import Optional, List


class PlaywrightBuildUtils:
    """Playwright 构建时工具类"""
    
    @staticmethod
    def get_default_browsers_path() -> Path:
        """获取默认的浏览器安装路径（构建时使用）"""
        if sys.platform == "darwin":  # macOS
            return Path.home() / ".cache" / "ms-playwright"
        elif sys.platform == "win32":  # Windows
            return Path.home() / "AppData" / "Local" / "ms-playwright"
        else:  # Linux
            return Path.home() / ".cache" / "ms-playwright"
    
    @staticmethod
    def get_app_data_path() -> Path:
        """获取应用数据目录（构建时使用）"""
        app_name = "eCan"
        if sys.platform == "darwin":  # macOS
            return Path.home() / "Library" / "Application Support" / app_name
        elif sys.platform == "win32":  # Windows
            return Path.home() / "AppData" / "Local" / app_name
        else:  # Linux
            return Path.home() / ".local" / "share" / app_name
    
    @staticmethod
    def get_possible_cache_paths() -> List[Path]:
        """获取所有可能的缓存路径（构建时查找）"""
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
        """验证浏览器安装是否有效（构建时验证）"""
        if not path or not path.exists():
            return False
        
        # 检查关键文件 - 更宽松的验证
        try:
            # 检查 browsers.json 文件
            browsers_json = path / "browsers.json"
            if not browsers_json.exists():
                return False
            
            # 检查是否有任何 chromium 相关目录
            chromium_dirs = list(path.glob("chromium*"))
            if not chromium_dirs:
                # 如果没有 chromium 目录，检查是否有其他浏览器目录
                browser_dirs = [d for d in path.iterdir() 
                              if d.is_dir() and not d.name.startswith('.')]
                if not browser_dirs:
                    return False
            
            # 检查目录是否包含实际文件（不是空目录）
            for browser_dir in chromium_dirs[:1]:  # 只检查第一个
                if browser_dir.is_dir():
                    files = list(browser_dir.rglob("*"))
                    if len(files) < 10:  # 至少应该有10个文件
                        return False
                    break
            
            return True
            
        except Exception as e:
            print(f"[BUILD] Validation error: {e}")
            return False
    
    @staticmethod
    def find_playwright_cache() -> Optional[Path]:
        """查找 Playwright 缓存目录（构建时查找）"""
        possible_roots = PlaywrightBuildUtils.get_possible_cache_paths()
        
        # 首先检查环境变量中设置的路径
        env_path = os.getenv("PLAYWRIGHT_BROWSERS_PATH")
        if env_path:
            env_path_obj = Path(env_path)
            if env_path_obj.exists() and (env_path_obj / "browsers.json").exists():
                return env_path_obj
        
        # 优先检查用户主目录下的缓存
        home_cache = Path.home() / ".cache" / "ms-playwright"
        if home_cache.exists() and (home_cache / "browsers.json").exists():
            return home_cache
        
        # 检查应用数据目录
        app_data_cache = PlaywrightBuildUtils.get_app_data_path() / "ms-playwright"
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
        """安装 Playwright 浏览器到指定路径（构建时安装）"""
        # 确保 playwright 包已安装
        try:
            subprocess.run([sys.executable, "-m", "pip", "show", "playwright"], 
                         check=True, capture_output=True)
        except subprocess.CalledProcessError:
            print("[BUILD] playwright not found; installing...")
            subprocess.run([sys.executable, "-m", "pip", "install", "playwright"], check=True)
        
        # 设置环境变量
        env = os.environ.copy()
        env["PLAYWRIGHT_BROWSERS_PATH"] = str(target_path)
        env["PLAYWRIGHT_CACHE_DIR"] = str(target_path)
        
        # 安装浏览器
        print("[BUILD] Installing chromium browser...")
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], 
                      check=True, env=env)
    
    @staticmethod
    def copy_playwright_browsers(src_path: Path, dst_path: Path) -> None:
        """复制 Playwright 浏览器文件（构建时复制，只保留当前平台需要的文件）"""
        if dst_path.exists():
            print(f"[BUILD] Cleaning existing {dst_path}")
            shutil.rmtree(dst_path, ignore_errors=True)
        
        print(f"[BUILD] Copying {src_path} -> {dst_path} (platform-specific)")
        
        # 创建目标目录
        dst_path.mkdir(parents=True, exist_ok=True)
        
        # 复制 browsers.json
        browsers_json_src = src_path / "browsers.json"
        if browsers_json_src.exists():
            shutil.copy2(browsers_json_src, dst_path / "browsers.json")
            print(f"[BUILD] Copied browsers.json")
        else:
            # 从 playwright 包复制 browsers.json
            try:
                import playwright
                playwright_package_dir = Path(playwright.__file__).parent / "driver" / "package"
                browsers_json_src = playwright_package_dir / "browsers.json"
                if browsers_json_src.exists():
                    shutil.copy2(browsers_json_src, dst_path / "browsers.json")
                    print(f"[BUILD] Copied browsers.json from playwright package")
                else:
                    print(f"[BUILD] Warning: browsers.json not found in playwright package")
            except Exception as e:
                print(f"[BUILD] Warning: Could not copy browsers.json: {e}")
        
        # 获取当前平台信息
        current_platform = PlaywrightBuildUtils.get_current_platform()
        print(f"[BUILD] Current platform: {current_platform}")
        
        # 只复制当前平台需要的浏览器文件
        PlaywrightBuildUtils._copy_platform_specific_browsers(src_path, dst_path, current_platform)
    
    @staticmethod
    def get_current_platform() -> str:
        """获取当前构建平台标识符"""
        system = platform.system().lower()
        machine = platform.machine().lower()
        
        if system == "darwin":
            if "arm" in machine or "aarch64" in machine:
                return "mac-arm64"
            else:
                return "mac-x64"
        elif system == "windows":
            if "arm" in machine or "aarch64" in machine:
                return "win-arm64"
            else:
                return "win-x64"
        elif system == "linux":
            if "arm" in machine or "aarch64" in machine:
                return "linux-arm64"
            else:
                return "linux-x64"
        else:
            return f"{system}-{machine}"
    
    @staticmethod
    def _copy_platform_specific_browsers(src_path: Path, dst_path: Path, target_platform: str) -> None:
        """复制平台特定的浏览器文件"""
        # 查找所有浏览器目录
        browser_dirs = list(src_path.glob("chromium-*"))
        
        for browser_dir in browser_dirs:
            if not browser_dir.is_dir():
                continue
                
            print(f"[BUILD] Processing browser directory: {browser_dir.name}")
            
            # 创建目标浏览器目录
            dst_browser_dir = dst_path / browser_dir.name
            dst_browser_dir.mkdir(exist_ok=True)
            
            # 复制 browsers.json（如果存在）
            browser_json = browser_dir / "browsers.json"
            if browser_json.exists():
                shutil.copy2(browser_json, dst_browser_dir / "browsers.json")
            
            # 查找并复制平台特定的浏览器
            platform_dirs = list(browser_dir.glob("*"))
            
            for platform_dir in platform_dirs:
                if not platform_dir.is_dir():
                    continue
                
                platform_name = platform_dir.name
                print(f"[BUILD] Found platform: {platform_name}")
                
                # 检查是否匹配当前平台
                if PlaywrightBuildUtils._is_platform_match(platform_name, target_platform):
                    print(f"[BUILD] Copying platform-specific files: {platform_name}")
                    
                    # 复制整个平台目录
                    dst_platform_dir = dst_browser_dir / platform_name
                    if dst_platform_dir.exists():
                        shutil.rmtree(dst_platform_dir)
                    shutil.copytree(platform_dir, dst_platform_dir)
                    
                    # 更新 browsers.json 中的路径信息
                    PlaywrightBuildUtils._update_browsers_json_paths(dst_browser_dir, platform_name)
                else:
                    print(f"[BUILD] Skipping non-matching platform: {platform_name}")
    
    @staticmethod
    def _is_platform_match(platform_name: str, target_platform: str) -> bool:
        """检查平台名称是否匹配目标平台"""
        # 平台名称映射
        platform_mapping = {
            "mac-arm64": ["mac-arm64", "mac-arm"],
            "mac-x64": ["mac-x64", "mac", "macos"],
            "win-arm64": ["win-arm64", "win-arm"],
            "win-x64": ["win-x64", "win", "windows"],
            "linux-arm64": ["linux-arm64", "linux-arm"],
            "linux-x64": ["linux-x64", "linux"]
        }
        
        target_platforms = platform_mapping.get(target_platform, [target_platform])
        
        # 检查是否匹配
        for target in target_platforms:
            if target.lower() in platform_name.lower():
                return True
        
        return False
    
    @staticmethod
    def _update_browsers_json_paths(browser_dir: Path, platform_name: str) -> None:
        """更新 browsers.json 中的路径信息，只保留当前平台"""
        browsers_json = browser_dir / "browsers.json"
        if not browsers_json.exists():
            return
        
        try:
            import json
            with open(browsers_json, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 过滤只保留当前平台的浏览器信息
            if 'browsers' in data:
                filtered_browsers = []
                for browser in data['browsers']:
                    if 'revision' in browser and 'name' in browser:
                        # 检查是否有当前平台的安装信息
                        if 'installByDefault' in browser:
                            # 对于 chromium，只保留当前平台
                            if browser['name'] == 'chromium':
                                # 查找当前平台的安装路径
                                platform_path = None
                                for key, value in browser.items():
                                    if isinstance(value, str) and platform_name in value:
                                        platform_path = value
                                        break
                                
                                if platform_path:
                                    # 创建新的浏览器信息，只包含当前平台
                                    new_browser = {
                                        'name': browser['name'],
                                        'revision': browser['revision'],
                                        'installByDefault': browser.get('installByDefault', True)
                                    }
                                    # 添加当前平台的路径
                                    new_browser[platform_name] = platform_path
                                    filtered_browsers.append(new_browser)
                        else:
                            # 保留没有 installByDefault 的浏览器
                            filtered_browsers.append(browser)
                
                data['browsers'] = filtered_browsers
            
            # 写回文件
            with open(browsers_json, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                
            print(f"[BUILD] Updated browsers.json for platform: {platform_name}")
            
        except Exception as e:
            print(f"[BUILD] Warning: Could not update browsers.json: {e}")
    
    @staticmethod
    def prepare_playwright_assets(target_path: Path) -> None:
        """准备 Playwright 资源（构建时专用）"""
        print("[BUILD] Ensuring playwright python package is installed...")
        
        # 安装 playwright 包
        try:
            subprocess.run([sys.executable, "-m", "pip", "show", "playwright"], 
                         check=True, capture_output=True)
        except subprocess.CalledProcessError:
            print("[BUILD] playwright not found; installing...")
            subprocess.run([sys.executable, "-m", "pip", "install", "playwright"], check=True)
        
        # 安装浏览器
        PlaywrightBuildUtils.install_playwright_browsers(PlaywrightBuildUtils.get_default_browsers_path())
        
        # 查找缓存
        src = PlaywrightBuildUtils.find_playwright_cache()
        if not src:
            raise RuntimeError("[BUILD] Unable to locate ms-playwright cache after install")
        
        # 复制到目标路径
        PlaywrightBuildUtils.copy_playwright_browsers(src, target_path)


# 构建时工具实例
build_utils = PlaywrightBuildUtils()
