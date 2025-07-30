#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ECBot 跨平台构建系统 v6.0
支持 macOS 和 Windows 双平台打包
单文件解决方案，集成所有构建功能
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
    """ECBot 跨平台构建器 - 支持 macOS 和 Windows"""

    def __init__(self, mode: str = "prod"):
        self.mode = mode  # dev 或 prod
        self.project_root = Path.cwd()
        self.config_file = Path(__file__).parent / "build_config.json"

        # 平台信息
        self.platform_name = platform.system()
        self.is_macos = self.platform_name == "Darwin"
        self.is_windows = self.platform_name == "Windows"

        # 加载配置
        self.base_config = self._load_config()

        # 设置路径
        self.build_dir = self.project_root / "build"
        self.dist_dir = self.project_root / "dist"
        self.cache_file = self.build_dir / "build_cache.json"

        # 确保目录存在
        self.build_dir.mkdir(exist_ok=True)

        # 加载缓存
        self.cache = self._load_cache()
    
    def _load_config(self) -> Dict[str, Any]:
        """从JSON文件加载配置"""
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"❌ 加载配置文件失败: {e}")
            print(f"配置文件路径: {self.config_file}")
            sys.exit(1)

    def get_platform_info(self) -> Dict[str, str]:
        """获取平台信息"""
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
        """获取构建配置 - 从JSON文件读取"""
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
        """检查构建前提条件"""
        print("🔍 检查构建前提条件...")

        # 检查 Python 版本
        if sys.version_info < (3, 8):
            print("❌ Python 版本过低，需要 3.8 或更高版本")
            return False

        # 检查 PyInstaller
        try:
            import PyInstaller
            print(f"✅ PyInstaller 版本: {PyInstaller.__version__}")
        except ImportError:
            print("❌ 未安装 PyInstaller，请运行: pip install pyinstaller")
            return False

        # 检查图标文件
        platform_info = self.get_platform_info()
        icon_path = self.project_root / platform_info["icon"]
        if not icon_path.exists():
            print(f"❌ 图标文件不存在: {icon_path}")
            return False

        print(f"✅ 平台: {platform_info['name']}")
        print(f"✅ 图标文件: {platform_info['icon']}")

        return True

    def build_frontend(self, skip_frontend: bool = False) -> bool:
        """构建前端"""
        if skip_frontend:
            print("⏭️  跳过前端构建 (使用 --skip-frontend 或 dev 模式默认)")
            # 检查是否存在已构建的前端文件
            gui_dist_path = self.project_root / "gui_v2" / "dist"
            if gui_dist_path.exists():
                print("✅ 使用现有前端构建文件")
                return True
            else:
                print("⚠️  未找到前端构建文件，将强制构建前端")

        print("🔨 构建前端...")

        gui_v2_path = self.project_root / "gui_v2"
        if not gui_v2_path.exists():
            print("❌ gui_v2 目录不存在")
            return False

        try:
            # 检查是否有 package.json
            if not (gui_v2_path / "package.json").exists():
                print("❌ gui_v2/package.json 不存在")
                return False

            print("📦 开始前端构建，这可能需要几分钟...")

            # 构建前端，显示详细输出
            result = subprocess.run(
                ["npm", "run", "build"],
                cwd=gui_v2_path,
                text=True,
                timeout=300
            )

            if result.returncode != 0:
                print(f"❌ 前端构建失败，返回码: {result.returncode}")
                return False

            print("✅ 前端构建完成")
            return True

        except subprocess.TimeoutExpired:
            print("❌ 前端构建超时 (5分钟)")
            return False
        except FileNotFoundError:
            print("❌ npm 命令未找到，请确保安装了 Node.js")
            return False
        except Exception as e:
            print(f"❌ 前端构建出错: {e}")
            return False

    def _load_cache(self) -> Dict[str, Any]:
        """加载构建缓存"""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'r') as f:
                    return json.load(f)
            except:
                pass
        return {"files": {}, "last_build": 0, "last_success": False}
    
    def _save_cache(self):
        """保存构建缓存"""
        with open(self.cache_file, 'w') as f:
            json.dump(self.cache, f, indent=2)
    
    def _get_file_hash(self, file_path: Path) -> str:
        """获取文件哈希"""
        try:
            with open(file_path, 'rb') as f:
                return hashlib.md5(f.read()).hexdigest()
        except:
            return ""
    
    def check_changes(self) -> bool:
        """检查文件是否有变更"""
        if self.mode == "prod":
            return True  # 生产模式总是重建
        
        print("🔍 检查文件变更...")
        
        # 检查关键文件
        key_files = [
            Path("main.py"), Path("app_context.py"),
            *[f for f in Path(".").glob("*.py") if f.is_file()],
            *[f for f in Path("bot").glob("**/*.py") if f.is_file()],
            *[f for f in Path("gui").glob("**/*.py") if f.is_file()],
            *[f for f in Path("agent").glob("**/*.py") if f.is_file()]
        ]
        
        changed = False
        for file_path in key_files[:50]:  # 限制检查文件数量
            if not file_path.exists():
                continue
                
            current_hash = self._get_file_hash(file_path)
            cached_hash = self.cache["files"].get(str(file_path), "")
            
            if current_hash != cached_hash:
                changed = True
                self.cache["files"][str(file_path)] = current_hash
        
        if not changed:
            print("✅ 未检测到变更，跳过构建")
            return False
        else:
            print("📝 检测到文件变更，需要重新构建")
            return True
    
    def clean_build(self):
        """清理构建目录"""
        if self.get_config()["clean"]:
            print("🧹 清理构建目录...")
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
                shutil.rmtree(self.dist_dir)
    
    def build(self, force: bool = False, skip_frontend: bool = None) -> bool:
        """执行完整构建流程"""
        platform_info = self.get_platform_info()
        print(f"🚀 ECBot 跨平台构建器 - {self.mode.upper()} 模式")
        print(f"🎯 目标平台: {platform_info['name']}")
        print("=" * 50)

        # 检查前提条件
        if not self.check_prerequisites():
            print("❌ 前提条件检查失败")
            return False

        # 决定是否跳过前端构建
        if skip_frontend is None:
            # dev 模式默认跳过前端构建
            skip_frontend = (self.mode == "dev")

        # 构建前端
        if not self.build_frontend(skip_frontend=skip_frontend):
            print("❌ 前端构建失败")
            return False

        # 检查是否需要构建后端
        if not force and not self.check_changes():
            print("✅ 无需重新构建后端")
            return True

        # 清理构建目录
        self.clean_build()

        # 开始构建后端
        print("🔨 开始构建后端...")
        start_time = time.time()
        
        try:
            success = self._run_pyinstaller()
            build_time = time.time() - start_time
            
            # 更新缓存
            self.cache["last_build"] = time.time()
            self.cache["last_success"] = success
            self.cache["last_duration"] = build_time
            self._save_cache()
            
            if success:
                print(f"✅ 构建完成 ({build_time:.1f}秒)")
                self._show_result()
            else:
                print("❌ 构建失败")
            
            return success
            
        except Exception as e:
            print(f"❌ 构建出错: {e}")
            return False
    
    def _run_pyinstaller(self) -> bool:
        """运行PyInstaller"""
        config = self.get_config()
        
        # 构建PyInstaller命令
        icon_path = str(self.project_root / config["icon"])
        cmd = [
            sys.executable, "-m", "PyInstaller",
            "--name", config["app_name"],
            "--icon", icon_path,
            "--workpath", str(self.build_dir / "work"),
            "--distpath", str(self.dist_dir),
            "--specpath", str(self.build_dir),
            "--noconfirm"  # 自动确认，不需要手动输入yes
        ]
        
        # 添加选项
        if config["debug"]:
            cmd.append("--debug=all")

        # 根据平台和模式决定窗口类型
        if self.is_macos:
            if config["console"] and self.mode == "dev":
                # dev 模式在 macOS 上使用 --console 以便调试
                cmd.append("--console")
                print("ℹ️  dev 模式使用 --console 以便调试 (生成目录而非 .app)")
            else:
                # 其他模式使用 --windowed 生成 .app 文件
                cmd.append("--windowed")
                if config["console"]:
                    print("ℹ️  macOS 生产模式使用 --windowed 生成 .app 文件")
        else:
            if config["console"]:
                cmd.append("--console")
            else:
                cmd.append("--windowed")
        if config["onefile"]:
            cmd.append("--onefile")
        else:
            cmd.append("--onedir")
        
        # 添加数据文件
        for data_dir in config["data_dirs"]:
            src_path = self.project_root / data_dir
            if src_path.exists():
                cmd.extend(["--add-data", f"{src_path}{os.pathsep}{data_dir}"])

        for data_file in config["data_files"]:
            src_path = self.project_root / data_file
            if src_path.exists():
                cmd.extend(["--add-data", f"{src_path}{os.pathsep}."])
        
        # 添加隐藏导入
        for module in config["hidden_imports"]:
            cmd.extend(["--hidden-import", module])

        # 特殊处理：添加tiktoken_ext包
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

        # 如果构建成功且是 macOS .app 文件，进行后处理
        if result.returncode == 0 and self.is_macos and not (self.mode == "dev" and config["console"]):
            self._post_process_macos_app()

        return result.returncode == 0

    def _post_process_macos_app(self):
        """macOS .app 文件后处理"""
        app_path = self.dist_dir / "ECBot.app"
        if not app_path.exists():
            return

        try:
            # 1. 优化 Info.plist
            self._optimize_info_plist(app_path)

            # 2. 设置正确的权限
            self._set_app_permissions(app_path)

        except Exception as e:
            print(f"⚠️  macOS .app 后处理失败: {e}")

    def _optimize_info_plist(self, app_path: Path):
        """优化 Info.plist 文件"""
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
            print(f"⚠️  Info.plist 优化失败: {e}")

    def _set_app_permissions(self, app_path: Path):
        """设置应用权限"""
        try:
            # 设置可执行文件权限
            executable_path = app_path / "Contents" / "MacOS" / "ECBot"
            if executable_path.exists():
                os.chmod(executable_path, 0o755)

            # 设置应用包权限
            os.chmod(app_path, 0o755)

        except Exception as e:
            print(f"⚠️  权限设置失败: {e}")

    def _show_result(self):
        """显示构建结果"""
        config = self.get_config()

        if self.is_macos:
            # 在 macOS 上，根据构建模式决定输出格式
            if self.mode == "dev" and config["console"]:
                # dev 模式生成目录
                app_path = self.dist_dir / "ECBot"
                if app_path.exists():
                    size = self._get_dir_size(app_path)
                    print(f"📁 macOS 应用目录 (dev模式): {app_path}")
                    print(f"📦 应用大小: {self._format_size(size)}")
                    print("ℹ️  dev 模式生成目录格式，便于调试")
                else:
                    print("❌ macOS 应用目录未找到")
            else:
                # 生产模式生成 .app 文件
                app_path = self.dist_dir / "ECBot.app"
                if app_path.exists():
                    size = self._get_dir_size(app_path)
                    print(f"📱 macOS 应用包: {app_path}")
                    print(f"📦 应用包大小: {self._format_size(size)}")
                else:
                    print("❌ macOS 应用包未找到")
        else:
            # Windows/Linux
            exe_path = self.dist_dir / "ECBot"
            if exe_path.exists():
                size = self._get_dir_size(exe_path)
                print(f"📁 应用目录: {exe_path}")
                print(f"📦 应用大小: {self._format_size(size)}")
            else:
                print("❌ 应用程序未找到")

        # 创建构建信息文件
        self._create_build_info()

    def _create_build_info(self):
        """创建构建信息文件"""
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

            print(f"📋 构建信息已保存: {build_info_path}")

        except Exception as e:
            print(f"⚠️  创建构建信息失败: {e}")



    def _get_dir_size(self, path: Path) -> int:
        """获取目录大小"""
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
        """格式化大小"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"
    
    def show_stats(self):
        """显示构建统计"""
        print("📊 构建统计:")
        print(f"  模式: {self.mode}")
        print(f"  缓存文件: {len(self.cache['files'])}")
        
        if self.cache["last_build"]:
            import datetime
            last_build = datetime.datetime.fromtimestamp(self.cache["last_build"])
            print(f"  上次构建: {last_build.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"  构建耗时: {self.cache.get('last_duration', 0):.1f}秒")
            print(f"  构建状态: {'成功' if self.cache['last_success'] else '失败'}")
        else:
            print("  上次构建: 从未构建")
    
    def clean_cache(self):
        """清理缓存"""
        print("🧹 清理构建缓存...")
        self.cache = {"files": {}, "last_build": 0, "last_success": False}
        self._save_cache()
        print("✅ 缓存已清理")


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="ECBot 跨平台构建系统 v6.0")
    parser.add_argument("mode", nargs="?", choices=["dev", "dev-debug", "prod"], default="prod",
                       help="构建模式: dev(开发) 或 dev-debug(调试) 或 prod(生产)")
    parser.add_argument("--force", action="store_true", help="强制重新构建")
    parser.add_argument("--skip-frontend", action="store_true", help="跳过前端构建")
    parser.add_argument("--build-frontend", action="store_true", help="强制构建前端 (覆盖 dev 模式默认)")
    parser.add_argument("--stats", action="store_true", help="显示构建统计")
    parser.add_argument("--clean-cache", action="store_true", help="清理构建缓存")

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
