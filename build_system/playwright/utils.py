#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Playwright build-time utilities module
Used exclusively for preparing Playwright assets at build time; no runtime logic here.
"""

import os
import sys
import shutil
import subprocess
import platform
from pathlib import Path
from typing import Optional, List


class PlaywrightBuildUtils:
    """Playwright build-time utilities"""
    
    @staticmethod
    def get_default_browsers_path() -> Path:
        """Get default browsers installation path (build-time)"""
        if sys.platform == "darwin":  # macOS
            return Path.home() / ".cache" / "ms-playwright"
        elif sys.platform == "win32":  # Windows
            return Path.home() / "AppData" / "Local" / "ms-playwright"
        else:  # Linux
            return Path.home() / ".cache" / "ms-playwright"
    
    @staticmethod
    def get_app_data_path() -> Path:
        """Get application data directory (build-time)"""
        app_name = "eCan"
        if sys.platform == "darwin":  # macOS
            return Path.home() / "Library" / "Application Support" / app_name
        elif sys.platform == "win32":  # Windows
            return Path.home() / "AppData" / "Local" / app_name
        else:  # Linux
            return Path.home() / ".local" / "share" / app_name
    
    @staticmethod
    def get_possible_cache_paths() -> List[Path]:
        """Get all possible cache paths (build-time search)"""
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
        
        # Also check current working directory
        possible_roots.append(Path.cwd() / ".ms-playwright")
        
        return possible_roots
    
    @staticmethod
    def validate_browser_installation(path: Path) -> bool:
        """Validate browser installation (build-time)"""
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
                # If no chromium directory, check for other browser directories
                browser_dirs = [d for d in path.iterdir() 
                              if d.is_dir() and not d.name.startswith('.')]
                if not browser_dirs:
                    return False

            # Check directory contains actual files (not empty)
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
        """Find Playwright cache directory (build-time search)"""
        possible_roots = PlaywrightBuildUtils.get_possible_cache_paths()
        
        # First check environment variables
        env_path = os.getenv("PLAYWRIGHT_BROWSERS_PATH")
        if env_path:
            env_path_obj = Path(env_path)
            if env_path_obj.exists() and (env_path_obj / "browsers.json").exists():
                return env_path_obj
        
        # Prefer cache under user home
        home_cache = Path.home() / ".cache" / "ms-playwright"
        if home_cache.exists() and (home_cache / "browsers.json").exists():
            return home_cache
        
        # Check app data directory
        app_data_cache = PlaywrightBuildUtils.get_app_data_path() / "ms-playwright"
        if app_data_cache.exists() and (app_data_cache / "browsers.json").exists():
            return app_data_cache
        
        # Then search other possible paths
        for root in possible_roots:
            if root.exists() and (root / "browsers.json").exists():
                return root
        
        # If browsers.json not found, look for directories containing chromium
        for root in possible_roots:
            if root.exists():
                chromium_dirs = list(root.glob("**/chromium*"))
                if chromium_dirs:
                    # Walk up to locate ms-playwright root
                    current = chromium_dirs[0].parent
                    while current.parent != current:  # 停止在根目录
                        if current.name == "ms-playwright":
                            return current
                        current = current.parent
        
        # Last resort: search for any ms-playwright directory
        search_paths = [Path.home(), Path.cwd()]
        for search_path in search_paths:
            if search_path.exists():
                for found in search_path.rglob("ms-playwright"):
                    if (found / "browsers.json").exists():
                        return found
        
        return None
    
    @staticmethod
    def install_playwright_browsers(target_path: Path) -> None:
        """Install Playwright browsers to specified path (build-time)"""
        # Ensure playwright package is installed
        try:
            subprocess.run([sys.executable, "-m", "pip", "show", "playwright"], 
                         check=True, capture_output=True)
        except subprocess.CalledProcessError:
            print("[BUILD] playwright not found; installing...")
            subprocess.run([sys.executable, "-m", "pip", "install", "playwright"], check=True)
        
        # Set environment variables
        env = os.environ.copy()
        env["PLAYWRIGHT_BROWSERS_PATH"] = str(target_path)
        env["PLAYWRIGHT_CACHE_DIR"] = str(target_path)
        
        # Install browser
        print("[BUILD] Installing chromium browser...")
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], 
                      check=True, env=env)
    
    @staticmethod
    def copy_playwright_browsers(src_path: Path, dst_path: Path) -> None:
        """Copy Playwright browser files (build-time copy; keep only current platform files)"""
        if dst_path.exists():
            print(f"[BUILD] Cleaning existing {dst_path}")
            shutil.rmtree(dst_path, ignore_errors=True)
        
        print(f"[BUILD] Copying {src_path} -> {dst_path} (platform-specific)")
        
        # Create destination directory
        dst_path.mkdir(parents=True, exist_ok=True)
        
        # Copy browsers.json
        browsers_json_src = src_path / "browsers.json"
        if browsers_json_src.exists():
            shutil.copy2(browsers_json_src, dst_path / "browsers.json")
            print(f"[BUILD] Copied browsers.json")
        else:
            # Copy browsers.json from playwright package
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
        
        # Get current platform info
        current_platform = PlaywrightBuildUtils.get_current_platform()
        print(f"[BUILD] Current platform: {current_platform}")
        
        # Copy only files required by current platform
        PlaywrightBuildUtils._copy_platform_specific_browsers(src_path, dst_path, current_platform)
    
    @staticmethod
    def get_current_platform() -> str:
        """Get current build platform identifier"""
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
        """Copy platform-specific browser files"""
        # 查找所有浏览器目录
        browser_dirs = list(src_path.glob("chromium-*"))
        
        for browser_dir in browser_dirs:
            if not browser_dir.is_dir():
                continue
                
            print(f"[BUILD] Processing browser directory: {browser_dir.name}")
            
            # Create destination browser directory
            dst_browser_dir = dst_path / browser_dir.name
            dst_browser_dir.mkdir(exist_ok=True)
            
            # Copy browsers.json (if exists)
            browser_json = browser_dir / "browsers.json"
            if browser_json.exists():
                shutil.copy2(browser_json, dst_browser_dir / "browsers.json")
            
            # Find and copy platform-specific browsers
            platform_dirs = list(browser_dir.glob("*"))
            
            for platform_dir in platform_dirs:
                if not platform_dir.is_dir():
                    continue
                
                platform_name = platform_dir.name
                print(f"[BUILD] Found platform: {platform_name}")
                
                # Check if matches current platform
                if PlaywrightBuildUtils._is_platform_match(platform_name, target_platform):
                    print(f"[BUILD] Copying platform-specific files: {platform_name}")
                    
                    # 复制整个平台目录
                    dst_platform_dir = dst_browser_dir / platform_name
                    if dst_platform_dir.exists():
                        shutil.rmtree(dst_platform_dir)
                    # Preserve symlinks inside Chromium.app and frameworks to avoid
                    # expanding them into real directories, which causes PyInstaller
                    # COLLECT collisions on macOS frameworks.
                    shutil.copytree(platform_dir, dst_platform_dir, symlinks=True)

                    # macOS: 保障 Framework 叶子目录为符号链接（避免后续被当作真实目录收集）
                    if sys.platform == "darwin":
                        try:
                            PlaywrightBuildUtils._ensure_framework_leaf_symlinks(dst_platform_dir)
                        except Exception as e:
                            print(f"[BUILD] Warning: ensure framework symlinks failed: {e}")
                    
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
        """Update browsers.json path info; keep only current platform"""
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
                        # Check if current platform has install info
                        if 'installByDefault' in browser:
                            # 对于 chromium，只保留当前平台
                            if browser['name'] == 'chromium':
                                # Find install path for current platform
                                platform_path = None
                                for key, value in browser.items():
                                    if isinstance(value, str) and platform_name in value:
                                        platform_path = value
                                        break
                                
                                if platform_path:
                                    # Create new browser info, current platform only
                                    new_browser = {
                                        'name': browser['name'],
                                        'revision': browser['revision'],
                                        'installByDefault': browser.get('installByDefault', True)
                                    }
                                    # Add current platform path
                                    new_browser[platform_name] = platform_path
                                    filtered_browsers.append(new_browser)
                        else:
                            # Keep browsers without installByDefault
                            filtered_browsers.append(browser)
                
                data['browsers'] = filtered_browsers
            
            # Write back file
            with open(browsers_json, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=True)
                
            print(f"[BUILD] Updated browsers.json for platform: {platform_name}")
            
        except Exception as e:
            print(f"[BUILD] Warning: Could not update browsers.json: {e}")

    @staticmethod
    def _ensure_framework_leaf_symlinks(platform_dir: Path) -> None:
        """Ensure *.framework leaf nodes (Headers/Resources/Modules/Helpers) are symlinks.
        If they were expanded as real directories, convert to symlink pointing to Versions/Current/<leaf>.
        """
        frameworks_root = platform_dir / "Chromium.app" / "Contents" / "Frameworks"
        if not frameworks_root.exists():
            return
        for fw in frameworks_root.iterdir():
            if not fw.is_dir() or not fw.name.endswith(".framework"):
                continue
            versions_current = fw / "Versions" / "Current"
            for leaf in ("Headers", "Resources", "Modules", "Helpers"):
                leaf_path = fw / leaf
                target = versions_current / leaf
                if leaf_path.exists() and not leaf_path.is_symlink():
                    # If target exists, replace directory with symlink
                    try:
                        if leaf_path.is_dir():
                            shutil.rmtree(leaf_path)
                        else:
                            leaf_path.unlink()
                    except Exception:
                        pass
                    if target.exists():
                        # Use relative link so bundle remains relocatable
                        rel = os.path.relpath(str(target), str(fw))
                        os.symlink(rel, str(leaf_path))
                        print(f"[BUILD] Fixed framework leaf to symlink: {leaf_path}")
    
    @staticmethod
    def prepare_playwright_assets(target_path: Path) -> None:
        """Prepare Playwright assets (build-time)"""
        print("[BUILD] Ensuring playwright python package is installed...")
        
        # Install playwright package
        try:
            subprocess.run([sys.executable, "-m", "pip", "show", "playwright"], 
                         check=True, capture_output=True)
        except subprocess.CalledProcessError:
            print("[BUILD] playwright not found; installing...")
            subprocess.run([sys.executable, "-m", "pip", "install", "playwright"], check=True)
        
        # Install browsers
        PlaywrightBuildUtils.install_playwright_browsers(PlaywrightBuildUtils.get_default_browsers_path())
        
        # Locate cache
        src = PlaywrightBuildUtils.find_playwright_cache()
        if not src:
            raise RuntimeError("[BUILD] Unable to locate ms-playwright cache after install")
        
        # Copy to target path
        PlaywrightBuildUtils.copy_playwright_browsers(src, target_path)


# Build-time utilities instance
build_utils = PlaywrightBuildUtils()
