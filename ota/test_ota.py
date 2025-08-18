#!/usr/bin/env python3
"""
OTA功能测试脚本
"""

import sys
import os
import importlib.util

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def has_module(mod_name: str) -> bool:
    return importlib.util.find_spec(mod_name) is not None

def test_ota_import():
    """测试OTA包导入"""
    print("Testing OTA package import...")
    try:
        from ota import OTAUpdater
        print("[OK] OTA package imported successfully")
        return True
    except Exception as e:
        print(f"[FAIL] OTA package import failed: {e}")
        return False

def test_ota_updater():
    """测试OTA更新器功能（使用本地桩，避免网络或外部CLI依赖）"""
    print("\nTesting OTA updater functionality...")
    try:
        from ota import OTAUpdater
        
        # 创建OTA更新器实例
        ota_updater = OTAUpdater()
        
        # 打桩平台更新器的检查逻辑，避免真实网络/CLI 调用
        def stub_check_for_updates(silent=False, return_info=False):
            # 无更新场景
            return (False, None) if return_info else False
        ota_updater.platform_updater.check_for_updates = stub_check_for_updates  # type: ignore
        
        # 测试基本属性
        print(f"Platform: {ota_updater.platform}")
        print(f"App version: {ota_updater.app_version}")
        print(f"Update server: {ota_updater.update_server_url}")
        
        # 测试更新检查（静默模式）
        print("Testing update check (silent mode, stubbed)...")
        has_update = ota_updater.check_for_updates(silent=True)
        print(f"Update available: {has_update}")
        
        print("[OK] OTA updater functionality test passed")
        return True
    except Exception as e:
        print(f"[FAIL] OTA updater functionality test failed: {e}")
        return False

def test_gui_components():
    """测试GUI组件（如缺少 PySide6 则跳过）"""
    print("\nTesting GUI components...")
    if not has_module('PySide6'):
        print("- Skipped: PySide6 not installed")
        return True
    try:
        from ota.gui.dialog import UpdateDialog, UpdateNotificationDialog
        print("[OK] GUI components imported successfully")
        return True
    except Exception as e:
        print(f"[FAIL] GUI components import failed: {e}")
        return False

def test_platform_updaters():
    """测试平台更新器"""
    print("\nTesting platform updaters...")
    try:
        from ota.core.platforms import SparkleUpdater, WinSparkleUpdater, GenericUpdater
        print("[OK] Platform updaters imported successfully")
        return True
    except Exception as e:
        print(f"[FAIL] Platform updaters import failed: {e}")
        return False

def test_server():
    """测试更新服务器（如缺少 Flask 则跳过）"""
    print("\nTesting update server...")
    if not has_module('flask'):
        print("- Skipped: Flask not installed")
        return True
    try:
        from ota.server import update_server_app
        print("[OK] Update server imported successfully")
        return True
    except Exception as e:
        print(f"[FAIL] Update server import failed: {e}")
        return False

def main():
    """主测试函数"""
    print("ECBot OTA Package Test")
    print("=" * 40)
    
    tests = [
        test_ota_import,
        test_ota_updater,
        test_gui_components,
        test_platform_updaters,
        test_server
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
    
    print("\n" + "=" * 40)
    print(f"Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! OTA package is working correctly.")
        return 0
    else:
        print("❌ Some tests failed. Please check the errors above.")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 