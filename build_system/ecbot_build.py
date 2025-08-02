#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ECBot Cross-Platform Build System v6.0
Supports macOS and Windows dual-platform packaging
Single file solution, integrates all build features
"""

import os
import sys
import json
import time
import hashlib
import subprocess
import platform
from pathlib import Path
from typing import Dict, Any, List


class ECBotBuild:
    """ECBot Cross-Platform Builder - Supports macOS and Windows"""

    def __init__(self, mode: str = "prod"):
        self.mode = mode  # dev or prod
        self.project_root = Path.cwd()
        self.config_file = Path(__file__).parent / "build_config.json"

        # Platform Info
        self.platform_name = platform.system()
        self.is_macos = self.platform_name == "Darwin"
        self.is_windows = self.platform_name == "Windows"

        # Load Config
        self.base_config = self._load_config()

        # Set Paths
        self.build_dir = self.project_root / "build"
        self.dist_dir = self.project_root / "dist"
        self.cache_file = self.build_dir / "build_cache.json"

        # Ensure directories exist
        self.build_dir.mkdir(exist_ok=True)

        # Load Cache
        self.cache = self._load_cache()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load Config from JSON file"""
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[ERROR] Load Config file failed: {e}")
            print(f"Config file path: {self.config_file}")
            sys.exit(1)

    def get_platform_info(self) -> Dict[str, str]:
        """Get Platform Info"""
        if self.is_macos:
            return {
                "name": "macOS",
                "icon": self.base_config["app_info"]["icon_macos"],
                "app_suffix": ".app",
                "executable_suffix": ""
            }
        elif self.is_windows:
            return {
                "name": "Windows",
                "icon": self.base_config["app_info"]["icon_windows"],
                "app_suffix": ".exe",
                "executable_suffix": ".exe"
            }
        else:
            return {
                "name": "Linux",
                "icon": self.base_config["app_info"]["icon_windows"],
                "app_suffix": "",
                "executable_suffix": ""
            }

    def get_config(self) -> Dict[str, Any]:
        """Get build config - read from JSON file"""
        platform_info = self.get_platform_info()

        config = {
            "app_name": self.base_config["app_info"]["name"],
            "main_script": self.base_config["app_info"]["main_script"],
            "icon": platform_info["icon"],
            "platform": platform_info,

            # 数据文件
            "data_dirs": self.base_config["data_files"]["directories"],
            "data_files": self.base_config["data_files"]["files"],

            # PyInstaller配置
            "excludes": self.base_config["pyinstaller"]["excludes"],
            "hidden_imports": self.base_config["pyinstaller"]["hidden_imports"]
        }

        # 模式特定配置
        mode_config = self.base_config["build_modes"][self.mode]
        config.update(mode_config)

        return config

    def check_prerequisites(self) -> bool:
        """Check build prerequisites"""
        print("Check build prerequisites...")

        # Check Python version
        if sys.version_info < (3, 8):
            print("[ERROR] Python version too low, requires 3.8 or higher")
            return False

        # Check PyInstaller
        try:
            import PyInstaller
            print(f"[SUCCESS] PyInstaller version: {PyInstaller.__version__}")
        except ImportError:
            print("[ERROR] PyInstaller not installed, please run: pip install pyinstaller")
            return False

        # 检查Icon file
        platform_info = self.get_platform_info()
        icon_path = self.project_root / platform_info["icon"]
        if not icon_path.exists():
            print(f"[ERROR] Icon file does not exist: {icon_path}")
            return False

        print(f"[SUCCESS] Platform: {platform_info['name']}")
        print(f"[SUCCESS] Icon file: {platform_info['icon']}")

        return True

    def build_frontend(self, skip_frontend: bool = False, force_frontend: bool = False) -> bool:
        """Build frontend"""
        if skip_frontend and not force_frontend:
            print("Skip frontend build (use --skip-frontend or dev mode default)")
            # 检查是否存在已构建的前端文件
            gui_dist_path = self.project_root / "gui_v2" / "dist"
            if gui_dist_path.exists():
                print("[SUCCESS] Using existing frontend build files")
                return True
            else:
                print("[WARNING]  Frontend build files not found, will force frontend build")
                force_frontend = True

        # 检查前端是否需要重新构建
        if not force_frontend and not skip_frontend:
            frontend_changed = self._check_frontend_changes()
            gui_dist_path = self.project_root / "gui_v2" / "dist"

            if not frontend_changed and gui_dist_path.exists():
                print("[SUCCESS] Frontend unchanged, using cached build files")
                return True

        print("[BUILD] Build frontend...")

        gui_v2_path = self.project_root / "gui_v2"
        if not gui_v2_path.exists():
            print("[ERROR] gui_v2 directory does not exist")
            return False

        try:
            # 检查是否有 package.json
            if not (gui_v2_path / "package.json").exists():
                print("[ERROR] gui_v2/package.json does not exist")
                return False

            print("Start frontend build, this may take a few minutes...")

            # 首先安装依赖
            print("[BUILD] Installing frontend dependencies...")
            install_result = subprocess.run(
                ["npm", "install", "--legacy-peer-deps"],
                cwd=gui_v2_path,
                text=True,
                timeout=300
            )

            if install_result.returncode != 0:
                print(f"[ERROR] Frontend dependency installation failed, return code: {install_result.returncode}")
                return False

            print("[SUCCESS] Frontend dependencies installed")

            # Build frontend，显示详细输出
            result = subprocess.run(
                ["npm", "run", "build"],
                cwd=gui_v2_path,
                text=True,
                timeout=300
            )

            if result.returncode != 0:
                print(f"[ERROR] Frontend build failed, return code: {result.returncode}")
                return False

            print("[SUCCESS] Frontend build completed")
            return True

        except subprocess.TimeoutExpired:
            print("[ERROR] Frontend build timeout (5 minutes)")
            return False
        except FileNotFoundError:
            print("[ERROR] npm command not found, please ensure Node.js is installed")
            print("[DEBUG] Checking Node.js installation...")
            try:
                # 尝试检查 node 是否可用
                node_result = subprocess.run(["node", "--version"], capture_output=True, text=True)
                if node_result.returncode == 0:
                    print(f"[DEBUG] Node.js version: {node_result.stdout.strip()}")
                else:
                    print("[DEBUG] Node.js not found")
            except:
                print("[DEBUG] Cannot check Node.js version")
            return False
        except Exception as e:
            print(f"[ERROR] Frontend build error: {e}")
            return False

    def _load_cache(self) -> Dict[str, Any]:
        """Load build cache"""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'r') as f:
                    return json.load(f)
            except:
                pass
        return {
            "files": {},
            "dependencies": {},
            "frontend": {},
            "last_build": 0,
            "last_success": False,
            "build_config_hash": "",
            "pyinstaller_spec_hash": "",
            "requirements_hash": ""
        }
    
    def _save_cache(self):
        """Save build cache"""
        with open(self.cache_file, 'w') as f:
            json.dump(self.cache, f, indent=2)
    
    def _get_file_hash(self, file_path: Path) -> str:
        """Get file hash"""
        try:
            with open(file_path, 'rb') as f:
                return hashlib.md5(f.read()).hexdigest()
        except:
            return ""

    def _get_directory_hash(self, dir_path: Path, extensions: List[str] = None) -> str:
        """获取目录内容哈希"""
        if not dir_path.exists():
            return ""

        if extensions is None:
            extensions = ['.py', '.json', '.txt', '.md', '.yml', '.yaml']

        file_hashes = []
        try:
            for file_path in sorted(dir_path.rglob('*')):
                if file_path.is_file() and any(file_path.suffix == ext for ext in extensions):
                    rel_path = file_path.relative_to(dir_path)
                    file_hash = self._get_file_hash(file_path)
                    file_hashes.append(f"{rel_path}:{file_hash}")

            combined = "|".join(file_hashes)
            return hashlib.md5(combined.encode()).hexdigest()
        except:
            return ""

    def _get_config_hash(self) -> str:
        """Get build config hash"""
        config_data = {
            "mode": self.mode,
            "base_config": self.base_config,
            "platform": self.get_platform_info()
        }
        config_str = json.dumps(config_data, sort_keys=True)
        return hashlib.md5(config_str.encode()).hexdigest()

    def _get_requirements_hash(self) -> str:
        """Get dependency file hash"""
        req_files = ["requirements-base.txt", "requirements-macos.txt", "requirements-windows.txt"]
        hashes = []
        for req_file in req_files:
            req_path = self.project_root / req_file
            if req_path.exists():
                hashes.append(self._get_file_hash(req_path))
        return hashlib.md5("|".join(hashes).encode()).hexdigest()
    
    def check_changes(self, force: bool = False) -> Dict[str, bool]:
        """Check if files have changes, return detailed change information"""
        changes = {
            "source_code": False,
            "dependencies": False,
            "config": False,
            "frontend": False,
            "any_change": False
        }

        if force:
            print("[FORCE] Force rebuild mode, skip change check")
            changes["any_change"] = True
            return changes

        print("Check incremental changes...")

        # 1. Check source code changes
        changes["source_code"] = self._check_source_changes()

        # 2. Check dependency changes
        changes["dependencies"] = self._check_dependency_changes()

        # 3. Check config changes
        changes["config"] = self._check_config_changes()

        # 4. Check frontend changes
        changes["frontend"] = self._check_frontend_changes()

        changes["any_change"] = any([
            changes["source_code"],
            changes["dependencies"],
            changes["config"]
        ])

        return changes

    def _check_source_changes(self) -> bool:
        """Check source code changes"""
        print("  Check source code changes...")

        # 检查关键目录
        key_dirs = ["bot", "gui", "agent", "common", "utils", "config"]
        key_files = ["main.py", "app_context.py"]

        changed = False

        # 检查关键文件
        for file_name in key_files:
            file_path = self.project_root / file_name
            if file_path.exists():
                current_hash = self._get_file_hash(file_path)
                cached_hash = self.cache["files"].get(str(file_path), "")
                if current_hash != cached_hash:
                    print(f"    [FORCE] File changed: {file_name}")
                    changed = True
                    self.cache["files"][str(file_path)] = current_hash

        # 检查关键目录
        for dir_name in key_dirs:
            dir_path = self.project_root / dir_name
            if dir_path.exists():
                current_hash = self._get_directory_hash(dir_path)
                cached_hash = self.cache["files"].get(f"dir:{dir_name}", "")
                if current_hash != cached_hash:
                    print(f"    [FORCE] Directory changed: {dir_name}/")
                    changed = True
                    self.cache["files"][f"dir:{dir_name}"] = current_hash

        if not changed:
            print("    [SUCCESS] Source code unchanged")

        return changed

    def _check_dependency_changes(self) -> bool:
        """Check dependency changes"""
        print("  Check dependency changes...")

        current_hash = self._get_requirements_hash()
        cached_hash = self.cache.get("requirements_hash", "")

        if current_hash != cached_hash:
            print("    [FORCE] Dependency file changed")
            self.cache["requirements_hash"] = current_hash
            return True
        else:
            print("    [SUCCESS] Dependencies unchanged")
            return False

    def _check_config_changes(self) -> bool:
        """Check config changes"""
        print("  Check config changes...")

        current_hash = self._get_config_hash()
        cached_hash = self.cache.get("build_config_hash", "")

        if current_hash != cached_hash:
            print("    [FORCE] Build config changed")
            self.cache["build_config_hash"] = current_hash
            return True
        else:
            print("    [SUCCESS] Config unchanged")
            return False

    def _check_frontend_changes(self) -> bool:
        """Check frontend changes"""
        print("  Check frontend changes...")

        # 确保 frontend 缓存存在
        if "frontend" not in self.cache:
            self.cache["frontend"] = {}

        frontend_dirs = ["gui_v2/src", "gui_v2/public"]
        frontend_files = ["gui_v2/package.json", "gui_v2/vite.config.ts", "gui_v2/tsconfig.json"]

        changed = False

        # 检查前端目录
        for dir_name in frontend_dirs:
            dir_path = self.project_root / dir_name
            if dir_path.exists():
                current_hash = self._get_directory_hash(dir_path, ['.ts', '.tsx', '.js', '.jsx', '.css', '.scss', '.json', '.html'])
                cached_hash = self.cache["frontend"].get(dir_name, "")
                if current_hash != cached_hash:
                    print(f"    [FORCE] Frontend directory changed: {dir_name}")
                    changed = True
                    self.cache["frontend"][dir_name] = current_hash

        # 检查前端配置文件
        for file_name in frontend_files:
            file_path = self.project_root / file_name
            if file_path.exists():
                current_hash = self._get_file_hash(file_path)
                cached_hash = self.cache["frontend"].get(file_name, "")
                if current_hash != cached_hash:
                    print(f"    [FORCE] Frontend config changed: {file_name}")
                    changed = True
                    self.cache["frontend"][file_name] = current_hash

        if not changed:
            print("    [SUCCESS] Frontend unchanged")

        return changed

    def _check_build_artifacts(self) -> bool:
        """Check build artifacts exist"""
        if self.is_macos:
            # macOS 检查 .app 文件或目录
            if self.mode == "dev":
                app_path = self.dist_dir / "ECBot"
            else:
                app_path = self.dist_dir / "ECBot.app"
        else:
            # Windows/Linux 检查目录
            app_path = self.dist_dir / "ECBot"

        return app_path.exists()

    def _show_change_summary(self, changes: Dict[str, bool]):
        """Show change summary"""
        print("Change summary:")

        change_items = [
            ("Source code", changes["source_code"]),
            ("Dependencies", changes["dependencies"]),
            ("Build config", changes["config"]),
            ("Frontend code", changes["frontend"])
        ]

        has_changes = False
        for name, changed in change_items:
            if changed:
                print(f"  [FORCE] {name}: has changes")
                has_changes = True
            else:
                print(f"  [SUCCESS] {name}: no changes")

        if not has_changes:
            print("  All components have no changes")

        print()

    def clean_build(self):
        """Clean build directory"""
        if self.get_config()["clean"]:
            print("[CLEAN] Clean build directory...")
            if self.build_dir.exists():
                import shutil
                for item in self.build_dir.iterdir():
                    if item.name != "build_cache.json":
                        if item.is_dir():
                            shutil.rmtree(item)
                        else:
                            item.unlink()

            if self.dist_dir.exists():
                import shutil
                # 先Delete所有文件和子目录
                for item in self.dist_dir.iterdir():
                    try:
                        if item.is_dir():
                            shutil.rmtree(item)
                        else:
                            item.unlink()
                    except Exception as e:
                        print(f"[WARNING]  Delete {item} error: {e}")

                # 然后Delete目录本身
                try:
                    self.dist_dir.rmdir()
                except Exception as e:
                    print(f"[WARNING]  Delete dist 目录error: {e}")
                    # 如果DeleteFailed，尝试强制Delete
                    try:
                        shutil.rmtree(self.dist_dir, ignore_errors=True)
                    except Exception as e2:
                        print(f"[WARNING]  Force delete dist directory also failed: {e2}")
    
    def build(self, force: bool = False, skip_frontend: bool = None) -> bool:
        """Execute complete build process"""
        platform_info = self.get_platform_info()
        print(f"[BUILD] ECBot Cross-Platform Builder - {self.mode.upper()} Mode")
        print(f"[TARGET] Platform: {platform_info['name']}")

        if force:
            print("[FORCE] Force Rebuild Mode")
        else:
            print("[INCREMENTAL] Incremental Build Mode")
        print("=" * 50)

        # Check prerequisites
        if not self.check_prerequisites():
            print("[ERROR] Prerequisites Check Failed")
            return False

        # Check changes
        changes = self.check_changes(force=force)

        # Decide whether to skip frontend build
        if skip_frontend is None:
            # dev mode skips frontend build by default
            skip_frontend = (self.mode == "dev")

        # Build frontend (根据变更情况决定是否强制重建)
        force_frontend = force or changes["frontend"]
        if not self.build_frontend(skip_frontend=skip_frontend, force_frontend=force_frontend):
            print("[ERROR] Frontend Build Failed")
            return False

        # Check if backend build is needed
        if not changes["any_change"]:
            # Check if build artifacts exist
            if self._check_build_artifacts():
                print("[SUCCESS] No changes and build artifacts exist, skipping backend build")
                self._show_result()
                return True
            else:
                print("[WARNING]  No changes but build artifacts missing, will rebuild")
                changes["any_change"] = True

        # Show change summary
        self._show_change_summary(changes)

        # Clean build directory (仅在has changes时)
        if changes["any_change"]:
            self.clean_build()

        # Start backend build
        print("[BUILD] Starting backend build...")
        start_time = time.time()

        try:
            success = self._run_pyinstaller()
            build_time = time.time() - start_time

            # Update cache
            self.cache["last_build"] = time.time()
            self.cache["last_success"] = success
            self.cache["last_duration"] = build_time
            self._save_cache()

            if success:
                print(f"[SUCCESS] Build completed ({build_time:.1f}s)")
                self._show_result()
            else:
                print("[ERROR] Build failed")

            return success

        except Exception as e:
            print(f"[ERROR] Build error: {e}")
            return False
    
    def _run_pyinstaller(self) -> bool:
        """Run PyInstaller"""
        config = self.get_config()
        
        # Build PyInstaller command
        icon_path = str(self.project_root / config["icon"])
        cmd = [
            sys.executable, "-m", "PyInstaller",
            "--name", config["app_name"],
            "--icon", icon_path,
            "--workpath", str(self.build_dir / "work"),
            "--distpath", str(self.dist_dir),
            "--specpath", str(self.build_dir),
            "--noconfirm"  # Auto confirm, no manual yes input needed
        ]
        
        # Add options
        if config["debug"]:
            cmd.append("--debug=all")

        # 根据Platform和模式决定窗口类型
        if self.is_macos:
            if config["console"] and self.mode == "dev":
                # dev mode uses --console on macOS for debugging
                cmd.append("--console")
                print("[INFO]  dev mode uses --console for debugging (Generate directory instead of .app)")
            else:
                # Other modes use --windowed to generate .app file
                cmd.append("--windowed")
                if config["console"]:
                    print("[INFO]  macOS production mode uses --windowed to generate .app file")
        else:
            if config["console"]:
                cmd.append("--console")
            else:
                cmd.append("--windowed")
        # Windows Platform在生产模式下使用 --onedir 以便 Inno Setup 打包
        if self.is_windows and self.mode == "prod":
            cmd.append("--onedir")
            print("[INFO]  Windows production mode uses --onedir for Inno Setup packaging")
        elif config["onefile"]:
            cmd.append("--onefile")
        else:
            cmd.append("--onedir")
        
        # Add data files
        for data_dir in config["data_dirs"]:
            src_path = self.project_root / data_dir
            if src_path.exists():
                cmd.extend(["--add-data", f"{src_path}{os.pathsep}{data_dir}"])

        for data_file in config["data_files"]:
            src_path = self.project_root / data_file
            if src_path.exists():
                cmd.extend(["--add-data", f"{src_path}{os.pathsep}."])
        
        # Add hidden imports
        for module in config["hidden_imports"]:
            cmd.extend(["--hidden-import", module])

        # Special handling: add tiktoken_ext package
        try:
            import tiktoken_ext
            tiktoken_ext_path = os.path.dirname(tiktoken_ext.__file__ or '') if tiktoken_ext.__file__ else ''
            if tiktoken_ext_path and os.path.exists(tiktoken_ext_path):
                cmd.extend(["--add-data", f"{tiktoken_ext_path}{os.pathsep}tiktoken_ext"])
                print(f"Added tiktoken_ext from: {tiktoken_ext_path}")
        except ImportError:
            print("Warning: tiktoken_ext not found, skipping...")

        # 特殊处理：添加scipy._lib.array_api_compat包
        try:
            import scipy._lib.array_api_compat
            scipy_compat_path = os.path.dirname(scipy._lib.array_api_compat.__file__)
            if scipy_compat_path and os.path.exists(scipy_compat_path):
                cmd.extend(["--add-data", f"{scipy_compat_path}{os.pathsep}scipy/_lib/array_api_compat"])
                print(f"Added scipy array_api_compat from: {scipy_compat_path}")
        except ImportError:
            print("Warning: scipy._lib.array_api_compat not found, skipping...")

        # 特殊处理：添加fake_useragent.data包
        try:
            import fake_useragent
            fake_useragent_path = os.path.dirname(fake_useragent.__file__ or '') if fake_useragent.__file__ else ''
            if fake_useragent_path and os.path.exists(fake_useragent_path):
                # 查找data目录
                data_path = os.path.join(fake_useragent_path, 'data')
                if os.path.exists(data_path):
                    cmd.extend(["--add-data", f"{data_path}{os.pathsep}fake_useragent/data"])
                    print(f"Added fake_useragent data from: {data_path}")
                else:
                    # 如果没有data目录，添加整个fake_useragent包
                    cmd.extend(["--add-data", f"{fake_useragent_path}{os.pathsep}fake_useragent"])
                    print(f"Added fake_useragent package from: {fake_useragent_path}")
        except ImportError:
            print("Warning: fake_useragent not found, skipping...")

        # 特殊处理：添加browser_use资源文件
        try:
            import browser_use
            browser_use_path = os.path.dirname(browser_use.__file__ or '') if browser_use.__file__ else ''
            if browser_use_path and os.path.exists(browser_use_path):
                # 查找prompts目录
                prompts_path = os.path.join(browser_use_path, 'agent', 'prompts')
                if os.path.exists(prompts_path):
                    cmd.extend(["--add-data", f"{prompts_path}{os.pathsep}browser_use/agent/prompts"])
                    print(f"Added browser_use prompts from: {prompts_path}")
                # 添加整个browser_use包以确保所有资源文件都被包含
                cmd.extend(["--add-data", f"{browser_use_path}{os.pathsep}browser_use"])
                print(f"Added browser_use package from: {browser_use_path}")
        except ImportError:
            print("Warning: browser_use not found, skipping...")

        # 多进程问题通过代码层面的修复来处理
        
        # 添加排除模块
        for module in config["excludes"]:
            cmd.extend(["--exclude-module", module])

        # macOS 特定配置
        if self.is_macos and not (self.mode == "dev" and config["console"]):
            # 为 .app 文件添加必要的配置
            cmd.extend([
                "--osx-bundle-identifier", "com.ecbot.app"
            ])

        # 添加主脚本
        cmd.append(config["main_script"])
        
        print(f"执行命令: {' '.join(cmd[:5])} ... (共{len(cmd)}个参数)")
        
        # 执行构建
        result = subprocess.run(cmd, cwd=self.project_root)

        # 如果构建Success且是 macOS .app 文件，进行后处理
        if result.returncode == 0 and self.is_macos and not (self.mode == "dev" and config["console"]):
            self._post_process_macos_app()

        return result.returncode == 0

    def _post_process_macos_app(self):
        """macOS .app file post-processing"""
        app_path = self.dist_dir / "ECBot.app"
        if not app_path.exists():
            return

        try:
            # 1. 优化 Info.plist
            self._optimize_info_plist(app_path)

            # 2. 设置正确的权限
            self._set_app_permissions(app_path)

        except Exception as e:
            print(f"[WARNING]  macOS .app post-processing failed: {e}")

    def _optimize_info_plist(self, app_path: Path):
        """Optimize Info.plist file"""
        plist_path = app_path / "Contents" / "Info.plist"
        if not plist_path.exists():
            return

        try:
            import plistlib

            # 读取现有的 plist
            with open(plist_path, 'rb') as f:
                plist_data = plistlib.load(f)

            # 添加必要的配置
            plist_data.update({
                'NSHighResolutionCapable': True,
                'LSMinimumSystemVersion': '10.13.0',
                'NSAppTransportSecurity': {
                    'NSAllowsArbitraryLoads': True
                },
                'NSCameraUsageDescription': 'ECBot needs camera access for automation tasks',
                'NSMicrophoneUsageDescription': 'ECBot needs microphone access for automation tasks',
                'NSAppleEventsUsageDescription': 'ECBot needs to control other applications for automation',
                'NSSystemAdministrationUsageDescription': 'ECBot needs system administration access for automation tasks'
            })

            # 写回 plist
            with open(plist_path, 'wb') as f:
                plistlib.dump(plist_data, f)

        except Exception as e:
            print(f"[WARNING]  Info.plist optimization failed: {e}")

    def _set_app_permissions(self, app_path: Path):
        """Set application permissions"""
        try:
            # 设置可执行文件权限
            executable_path = app_path / "Contents" / "MacOS" / "ECBot"
            if executable_path.exists():
                os.chmod(executable_path, 0o755)

            # 设置应用包权限
            os.chmod(app_path, 0o755)

        except Exception as e:
            print(f"[WARNING]  Permission setting failed: {e}")

    def _show_result(self):
        """Show build result"""
        config = self.get_config()

        if self.is_macos:
            # 在 macOS 上，根据构建模式决定输出格式
            if self.mode == "dev" and config["console"]:
                # dev 模式生成目录
                app_path = self.dist_dir / "ECBot"
                if app_path.exists():
                    size = self._get_dir_size(app_path)
                    print(f"macOS app directory (dev mode): {app_path}")
                    print(f"App size: {self._format_size(size)}")
                    print("[INFO]  dev mode generates directory format for debugging")
                else:
                    print("[ERROR] macOS app directory not found")
            else:
                # 生产模式生成 .app 文件
                app_path = self.dist_dir / "ECBot.app"
                if app_path.exists():
                    size = self._get_dir_size(app_path)
                    print(f"macOS app package: {app_path}")
                    print(f"App package size: {self._format_size(size)}")
                else:
                    print("[ERROR] macOS app package not found")
        else:
            # Windows/Linux
            exe_path = self.dist_dir / "ECBot"
            if exe_path.exists():
                size = self._get_dir_size(exe_path)
                print(f"📁 Application directory: {exe_path}")
                print(f"📦 Application size: {self._format_size(size)}")
                
                # Windows Platform尝试Create installer
                if self.is_windows and self.mode == "prod":
                    self._create_installer()
            else:
                print("[ERROR] Application not found")

        # Create build info文件
        self._create_build_info()

    def _create_installer(self):
        """Create Windows installer"""
        try:
            print("🔧 Start creating Windows installer...")
            
            # 检查是否启用安装包创建
            installer_config = self.base_config.get("installer", {})
            if not installer_config.get("enabled", True):
                print("[INFO]  Installer creation disabled, skipping")
                return
            
            # Check if Inno Setup is available
            if not self._check_inno_setup():
                print("[WARNING]  Inno Setup not installed, skip installer creation")
                print("Please install Inno Setup: https://jrsoftware.org/isinfo.php")
                return
            
            # Create Inno Setup script
            iss_file = self._create_inno_script()
            if not iss_file:
                print("[ERROR] Failed to create Inno Setup script")
                return
            
            # Run Inno Setup 编译
            if self._run_inno_setup(iss_file):
                print("[SUCCESS] Windows installer created successfully")
            else:
                print("[ERROR] Windows installer creation failed")
                
        except Exception as e:
            print(f"[WARNING]  Create installererror: {e}")

    def _check_inno_setup(self) -> bool:
        """Check if Inno Setup is available"""
        try:
            # Check Inno Setup 编译器
            result = subprocess.run(
                ["iscc", "/?"], 
                capture_output=True, 
                text=True, 
                timeout=10
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def _create_inno_script(self) -> Path:
        """Create Inno Setup script"""
        try:
            config = self.get_config()
            app_name = config["app_name"]
            installer_config = self.base_config.get("installer", {})
            
            # 准备路径
            dist_dir_str = str(self.dist_dir).replace('/', '\\')
            icon_path = str(self.project_root / config['icon']).replace('/', '\\')
            
            iss_content = f"""[Setup]
AppName={installer_config.get('app_name', app_name)}
AppVersion={installer_config.get('app_version', '1.0.0')}
AppPublisher={installer_config.get('app_publisher', 'ECBot Team')}
AppPublisherURL={installer_config.get('app_publisher_url', 'https://github.com/your-repo/ecbot')}
AppSupportURL={installer_config.get('app_support_url', 'https://github.com/your-repo/ecbot/issues')}
AppUpdatesURL={installer_config.get('app_updates_url', 'https://github.com/your-repo/ecbot/releases')}
DefaultDirName={{autopf}}\\{app_name}
DefaultGroupName={app_name}
AllowNoIcons=yes
OutputDir={dist_dir_str}
OutputBaseFilename={app_name}-Setup
SetupIconFile={icon_path}
Compression={installer_config.get('compression', 'lzma')}
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "chinesesimp"; MessagesFile: "compiler:Languages\\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "{{cm:CreateDesktopIcon}}"; GroupDescription: "{{cm:AdditionalIcons}}"; Flags: unchecked

[Files]
Source: "{dist_dir_str}\\{app_name}\\*"; DestDir: "{{app}}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{{group}}\\{app_name}"; Filename: "{{app}}\\{app_name}.exe"
Name: "{{group}}\\Uninstall {app_name}"; Filename: "{{uninstallexe}}"
Name: "{{commondesktop}}\\{app_name}"; Filename: "{{app}}\\{app_name}.exe"; Tasks: desktopicon

[Run]
Filename: "{{app}}\\{app_name}.exe"; Description: "{{cm:LaunchProgram,{app_name}}}"; Flags: nowait postinstall skipifsilent
"""
            
            # 保存脚本文件
            iss_file = self.dist_dir / f"{app_name}.iss"
            with open(iss_file, "w", encoding="utf-8") as f:
                f.write(iss_content)
            
            print(f"Inno Setup script created: {iss_file}")
            return iss_file
            
        except Exception as e:
            print(f"[ERROR] Failed to create Inno Setup script: {e}")
            return None

    def _run_inno_setup(self, iss_file: Path) -> bool:
        """Run Inno Setup compilation"""
        try:
            print(f"[BUILD] Compiling installer: {iss_file}")
            
            # Run Inno Setup 编译器
            result = subprocess.run(
                ["iscc", str(iss_file)],
                cwd=self.dist_dir,
                capture_output=True,
                text=True,
                timeout=300  # 5分钟超时
            )
            
            if result.returncode == 0:
                # 查找生成的安装包
                setup_files = list(self.dist_dir.glob("*-Setup.exe"))
                if setup_files:
                    setup_file = setup_files[0]
                    size = setup_file.stat().st_size
                    print(f"Installer created: {setup_file}")
                    print(f"Installer size: {self._format_size(size)}")
                    return True
                else:
                    print("[WARNING]  Compilation successful but installer file not found")
                    return False
            else:
                print(f"[ERROR] Inno Setup compilation failed:")
                print(f"Error output: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            print("[ERROR] Inno Setup compilation timeout")
            return False
        except Exception as e:
            print(f"[ERROR] Inno Setup compilation error: {e}")
            return False

    def _create_build_info(self):
        """Create build info file"""
        try:
            platform_info = self.get_platform_info()
            build_info = {
                "app_name": self.base_config["app_info"]["name"],
                "version": "1.0.0",  # 可以从配置文件读取
                "platform": {
                    "name": platform_info["name"],
                    "system": self.platform_name,
                    "architecture": platform.machine()
                },
                "build": {
                    "mode": self.mode,
                    "python_version": platform.python_version(),
                    "build_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "builder": "ECBot Build System v6.0"
                }
            }

            build_info_path = self.dist_dir / "build_info.json"
            with open(build_info_path, "w", encoding="utf-8") as f:
                json.dump(build_info, f, indent=2, ensure_ascii=False)

            print(f"Build info saved: {build_info_path}")

        except Exception as e:
            print(f"[WARNING]  Failed to create build info: {e}")



    def _get_dir_size(self, path: Path) -> int:
        """Get directory size"""
        total = 0
        try:
            for dirpath, _, filenames in os.walk(path):
                for filename in filenames:
                    file_path = Path(dirpath) / filename
                    if file_path.exists():
                        total += file_path.stat().st_size
        except:
            pass
        return total
    
    def _format_size(self, size: int) -> str:
        """Format size"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"
    
    def show_stats(self):
        """Show Build Statistics"""
        print("Build Statistics:")
        print(f"  Build mode: {self.mode}")
        print(f"  Platform: {self.get_platform_info()['name']}")
        print()

        print("Cache info:")
        print(f"  Source code files: {len([k for k in self.cache.get('files', {}).keys() if not k.startswith('dir:')])}")
        print(f"  Monitor directory: {len([k for k in self.cache.get('files', {}).keys() if k.startswith('dir:')])}")
        print(f"  Frontend files: {len(self.cache.get('frontend', {}))}")
        print(f"  Dependencies hash: {'Cached' if self.cache.get('requirements_hash') else 'Not cached'}")
        print(f"  Build config hash: {'Cached' if self.cache.get('build_config_hash') else 'Not cached'}")
        print()

        if self.cache.get("last_build"):
            import datetime
            last_build = datetime.datetime.fromtimestamp(self.cache["last_build"])
            print("Last build:")
            print(f"  Time: {last_build.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"  Duration: {self.cache.get('last_duration', 0):.1f}秒")
            print(f"  Status: {'[SUCCESS] Success' if self.cache.get('last_success') else '[ERROR] Failed'}")
        else:
            print("Last build: Never built")

        print()

        # 检查当前变更Status
        print("Current status check:")
        changes = self.check_changes(force=False)
        if changes["any_change"]:
            print("  Changes detected, suggest rebuilding")
        else:
            if self._check_build_artifacts():
                print("  [SUCCESS] no changes and build artifacts exist")
            else:
                print("  [WARNING]  no changes but build artifacts missing")

        print()
        print("Tips:")
        print("  - Use --force to force a complete rebuild")
        print("  - Use --clean-cache to clean cache")
        print("  - Incremental build can significantly improve build speed")
    
    def clean_cache(self):
        """Clean cache"""
        print("[CLEAN] Clean build cache...")
        self.cache = {"files": {}, "last_build": 0, "last_success": False}
        self._save_cache()
        print("[SUCCESS] Cache cleaned")


def main():
    """Main function"""
    import argparse

    parser = argparse.ArgumentParser(
        description="ECBot Cross-Platform Build System v6.0 - Support smart incremental build",
        epilog="""
Incremental build instructions:
  By default, the build system checks for changes in source code, dependencies, and configuration. It only rebuilds when changes are detected.
  Use --force to force a complete rebuild.

Examples:
  python ecbot_build.py prod              # Incremental build in production mode
  python ecbot_build.py dev --force       # Force rebuild in development mode
  python ecbot_build.py prod --stats      # View Build Statistics
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("mode", nargs="?", choices=["dev", "dev-debug", "prod"], default="prod",
                       help="Build mode: dev(development) or dev-debug(debug) or prod(production)")
    parser.add_argument("--force", action="store_true",
                       help="Force rebuild (skip incremental check)")
    parser.add_argument("--skip-frontend", action="store_true",
                       help="Skip frontend build")
    parser.add_argument("--build-frontend", action="store_true",
                       help="Force build frontend (override dev mode default)")
    parser.add_argument("--stats", action="store_true",
                       help="Show Build Statistics information")
    parser.add_argument("--clean-cache", action="store_true",
                       help="Clean build cache and exit")

    args = parser.parse_args()

    builder = ECBotBuild(args.mode)

    if args.clean_cache:
        builder.clean_cache()
        return

    if args.stats:
        builder.show_stats()
        return

    # 决定前端构建策略
    skip_frontend = None
    if args.skip_frontend:
        skip_frontend = True
    elif args.build_frontend:
        skip_frontend = False
    # 否则使用默认策略 (dev 模式跳过，其他模式构建)

    # 执行构建
    success = builder.build(force=args.force, skip_frontend=skip_frontend)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
