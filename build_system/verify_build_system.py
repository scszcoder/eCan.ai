#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ECBot 构建系统健康检查脚本
统一系统完整性、最终检查、详细报告功能
"""

import os
import sys
import platform
import subprocess
import json
from pathlib import Path
from typing import List, Dict, Tuple

class BuildSystemVerifier:
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.system = platform.system()
        self.is_windows = self.system == "Windows"
        self.is_macos = self.system == "Darwin"
        self.verification_results = []

    def log_result(self, test_name: str, success: bool, message: str = ""):
        status = "✓" if success else "✗"
        result = {
            "test": test_name,
            "success": success,
            "message": message,
            "status": status
        }
        self.verification_results.append(result)
        print(f"{status} {test_name}: {message}")

    def check_required_files(self) -> bool:
        print("\n=== 检查必需文件 ===")
        required_files = [
            "main.py",
            "build_system/ecbot_build.py",
            "requirements-base.txt",
            "requirements-windows.txt",
            "requirements-macos.txt"
        ]
        success = True
        for file_path in required_files:
            if (self.project_root / file_path).exists():
                self.log_result(f"文件存在: {file_path}", True)
            else:
                self.log_result(f"文件存在: {file_path}", False, "文件缺失")
                success = False
        return success

    def check_optional_files(self) -> bool:
        print("\n=== 检查可选文件 ===")
        optional_files = [
            ("ECBot.ico", "Windows图标文件"),
            ("ECBot.icns", "macOS图标文件")
        ]
        success = True
        for file_path, description in optional_files:
            if (self.project_root / file_path).exists():
                self.log_result(f"{description}: {file_path}", True)
            else:
                self.log_result(f"{description}: {file_path}", False, "文件缺失")
                success = False
        return success

    def check_configuration(self) -> bool:
        print("\n=== 检查配置文件 ===")
        config_file = self.project_root / "build_system/build_config.json"
        if not config_file.exists():
            self.log_result("配置文件", False, "build_config.json 不存在")
            return False
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            required_keys = ["app_info", "data_files", "excluded_modules", "hidden_imports"]
            success = True
            for key in required_keys:
                if key in config:
                    self.log_result(f"配置项: {key}", True)
                else:
                    self.log_result(f"配置项: {key}", False, "配置项缺失")
                    success = False
            if "app_info" in config:
                app_info = config["app_info"]
                if "name" in app_info and "version" in app_info:
                    self.log_result("应用信息配置", True)
                else:
                    self.log_result("应用信息配置", False, "缺少name或version")
                    success = False
            return success
        except Exception as e:
            self.log_result("配置文件解析", False, f"JSON解析错误: {e}")
            return False

    def check_dependencies(self) -> bool:
        print("\n=== 检查Python依赖 ===")
        if sys.version_info >= (3, 8):
            self.log_result("Python版本", True, f"版本 {sys.version_info.major}.{sys.version_info.minor}")
        else:
            self.log_result("Python版本", False, f"版本过低: {sys.version_info.major}.{sys.version_info.minor}")
            return False
        critical_modules = [
            ("pathlib", "标准库"),
            ("subprocess", "标准库"),
            ("json", "标准库"),
            ("argparse", "标准库")
        ]
        success = True
        for module, description in critical_modules:
            try:
                __import__(module)
                self.log_result(f"模块: {module}", True, description)
            except ImportError:
                self.log_result(f"模块: {module}", False, f"{description} - 导入失败")
                success = False
        return success

    def check_build_scripts(self) -> bool:
        print("\n=== 检查构建脚本 ===")
        scripts = [
            ("build_system/ecbot_build.py", "极简构建器"),
            ("build_system/verify_build_system.py", "健康检查脚本"),
            ("build_system/core/platform_handler.py", "平台处理器")
        ]
        success = True
        for script, description in scripts:
            script_path = self.project_root / script
            if script_path.exists():
                try:
                    with open(script_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        if "#!/usr/bin/env python" in content or "python" in content or "class " in content:
                            self.log_result(f"脚本: {script}", True, description)
                        else:
                            self.log_result(f"脚本: {script}", False, "无效的Python文件")
                            success = False
                except Exception as e:
                    self.log_result(f"脚本: {script}", False, f"读取失败: {e}")
                    success = False
            else:
                self.log_result(f"脚本: {script}", False, "文件不存在")
                success = False
        return success

    def check_platform_specific(self) -> bool:
        print("\n=== 检查平台特定功能 ===")
        success = True
        if self.is_windows:
            if (self.project_root / "build_system/build.bat").exists():
                self.log_result("Windows构建脚本", True)
            else:
                self.log_result("Windows构建脚本", False, "build_system/build.bat 不存在")
                success = False
            if (self.project_root / "ECBot.ico").exists():
                self.log_result("Windows图标", True)
            else:
                self.log_result("Windows图标", False, "ECBot.ico 不存在")
                success = False
        elif self.is_macos:
            if (self.project_root / "build_system/build.sh").exists():
                self.log_result("macOS构建脚本", True)
            else:
                self.log_result("macOS构建脚本", False, "build_system/build.sh 不存在")
                success = False
            if (self.project_root / "ECBot.icns").exists():
                self.log_result("macOS图标", True)
            else:
                self.log_result("macOS图标", False, "ECBot.icns 不存在")
                success = False
        return success

    def check_data_files(self) -> bool:
        print("\n=== 检查数据文件 ===")
        config_file = self.project_root / "build_system/build_config.json"
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            data_files = config.get("data_files", [])
            success = True
            for item in data_files:
                if isinstance(item, dict):
                    src = item.get("src")
                    dst = item.get("dst")
                else:
                    src, dst = item
                src_path = self.project_root / src
                if src_path.exists():
                    self.log_result(f"数据文件: {src}", True, f"目标: {dst}")
                else:
                    self.log_result(f"数据文件: {src}", False, "文件不存在")
                    success = False
            return success
        except Exception as e:
            self.log_result("数据文件检查", False, f"配置读取错误: {e}")
            return False

    def check_build_output(self) -> bool:
        print("\n=== 检查打包产物 ===")
        dist_dir = self.project_root / "dist"
        app_name = "ECBot"
        exe_path_win = dist_dir / app_name.lower() / f"{app_name.lower()}.exe"
        exe_path_mac = dist_dir / app_name.lower() / app_name.lower()
        app_path_mac = dist_dir / f"{app_name}.app"
        success = True
        if self.is_windows:
            if exe_path_win.exists():
                self.log_result("Windows可执行文件", True, str(exe_path_win))
            else:
                self.log_result("Windows可执行文件", False, str(exe_path_win))
                success = False
        if self.is_macos:
            if exe_path_mac.exists():
                self.log_result("macOS可执行文件", True, str(exe_path_mac))
            else:
                self.log_result("macOS可执行文件", False, str(exe_path_mac))
                success = False
            if app_path_mac.exists():
                self.log_result("macOS应用包", True, str(app_path_mac))
            else:
                self.log_result("macOS应用包", False, str(app_path_mac))
                success = False
        return success

    def run_all_checks(self) -> bool:
        print("\n🎯 ECBot 构建系统健康检查")
        print("=" * 60)
        print(f"系统: {self.system}")
        print(f"Python版本: {sys.version}")
        print(f"项目路径: {self.project_root}")
        print("=" * 60)
        checks = [
            ("必需文件检查", self.check_required_files),
            ("可选文件检查", self.check_optional_files),
            ("配置文件检查", self.check_configuration),
            ("依赖检查", self.check_dependencies),
            ("构建脚本检查", self.check_build_scripts),
            ("平台特定检查", self.check_platform_specific),
            ("数据文件检查", self.check_data_files),
            ("打包产物检查", self.check_build_output)
        ]
        all_passed = True
        for name, func in checks:
            try:
                if not func():
                    all_passed = False
            except Exception as e:
                self.log_result(name, False, f"检查异常: {e}")
                all_passed = False
        return all_passed

    def generate_report(self):
        print("\n=== 生成健康检查报告 ===")
        total = len(self.verification_results)
        passed = sum(1 for r in self.verification_results if r["success"])
        failed = total - passed
        print(f"总检查数: {total}")
        print(f"通过: {passed}")
        print(f"失败: {failed}")
        print(f"成功率: {passed/total*100:.1f}%")
        if failed > 0:
            print("\n失败项:")
            for r in self.verification_results:
                if not r["success"]:
                    print(f"  - {r['test']}: {r['message']}")
        report_file = self.project_root / "build_system" / "build_system_health_report.txt"
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write("ECBot 构建系统健康检查报告\n")
            f.write("="*50+"\n")
            f.write(f"系统: {self.system}\n")
            f.write(f"Python版本: {sys.version}\n")
            f.write(f"检查时间: {__import__('datetime').datetime.now()}\n\n")
            for r in self.verification_results:
                f.write(f"{r['status']} {r['test']}: {r['message']}\n")
            f.write(f"\n总检查数: {total}\n通过: {passed}\n失败: {failed}\n成功率: {passed/total*100:.1f}%\n")
        print(f"\n详细报告已保存到: {report_file}")
        return failed == 0


def main():
    verifier = BuildSystemVerifier()
    all_passed = verifier.run_all_checks()
    success = verifier.generate_report()
    if all_passed and success:
        print("\n🎉 构建系统健康检查全部通过！可以开始构建应用。")
        print("下一步: python build.py build --clean 或 python build.py start")
        sys.exit(0)
    else:
        print("\n❌ 构建系统健康检查未通过，请根据报告修复问题后重试。")
        sys.exit(1)

if __name__ == "__main__":
    main() 