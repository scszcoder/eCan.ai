#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ECBot 极简构建系统 v5.0
单文件解决方案，集成所有构建功能
"""

import os
import sys
import json
import time
import hashlib
import subprocess
from pathlib import Path
from typing import Dict, Any, List


class ECBotBuild:
    """ECBot 极简构建器 - 单文件解决方案"""
    
    def __init__(self, mode: str = "prod"):
        self.mode = mode  # dev 或 prod
        self.project_root = Path.cwd()
        self.config_file = Path(__file__).parent / "build_config.json"

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

    def get_config(self) -> Dict[str, Any]:
        """获取构建配置 - 从JSON文件读取"""
        config = {
            "app_name": self.base_config["app_info"]["name"],
            "main_script": self.base_config["app_info"]["main_script"],
            "icon": self.base_config["app_info"]["icon"],

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
    
    def build(self, force: bool = False) -> bool:
        """执行构建"""
        print(f"🚀 ECBot 构建器 - {self.mode.upper()} 模式")
        print("=" * 50)
        
        # 检查是否需要构建
        if not force and not self.check_changes():
            return True
        
        # 清理构建目录
        self.clean_build()
        
        # 开始构建
        print("🔨 开始构建...")
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
        cmd = [
            sys.executable, "-m", "PyInstaller",
            "--name", config["app_name"],
            "--icon", config["icon"],
            "--workpath", str(self.build_dir / "work"),
            "--distpath", str(self.dist_dir),
            "--specpath", str(self.build_dir),
            "--noconfirm"  # 自动确认，不需要手动输入yes
        ]
        
        # 添加选项
        if config["debug"]:
            cmd.append("--debug=all")
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
        
        # 添加主脚本
        cmd.append(config["main_script"])
        
        print(f"执行命令: {' '.join(cmd[:5])} ... (共{len(cmd)}个参数)")
        
        # 执行构建
        result = subprocess.run(cmd, cwd=self.project_root)
        return result.returncode == 0
    
    def _show_result(self):
        """显示构建结果"""
        app_path = self.dist_dir / "ECBot.app"
        if app_path.exists():
            size = self._get_dir_size(app_path)
            print(f"📱 应用包大小: {self._format_size(size)}")
        else:
            exe_path = self.dist_dir / "ECBot"
            if exe_path.exists():
                size = self._get_dir_size(exe_path)
                print(f"📁 应用目录大小: {self._format_size(size)}")
    
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
    
    parser = argparse.ArgumentParser(description="ECBot 极简构建系统 v5.0")
    parser.add_argument("mode", nargs="?", choices=["dev", "prod"], default="prod",
                       help="构建模式: dev(开发) 或 prod(生产)")
    parser.add_argument("--force", action="store_true", help="强制重新构建")
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
    
    # 执行构建
    success = builder.build(force=args.force)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
