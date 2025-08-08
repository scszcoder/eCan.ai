#!/usr/bin/env python3
"""
OTA功能测试脚本
"""

import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_ota_import():
    """测试OTA包导入"""
    print("Testing OTA package import...")
    try:
        from ota import OTAUpdater
        print("✓ OTA package imported successfully")
        return True
    except Exception as e:
        print(f"✗ OTA package import failed: {e}")
        return False

def test_ota_updater():
    """测试OTA更新器功能"""
    print("\nTesting OTA updater functionality...")
    try:
        from ota import OTAUpdater
        
        # 创建OTA更新器实例
        ota_updater = OTAUpdater()
        
        # 测试基本属性
        print(f"Platform: {ota_updater.platform}")
        print(f"App version: {ota_updater.app_version}")
        print(f"Update server: {ota_updater.update_server_url}")
        
        # 测试更新检查（静默模式）
        print("Testing update check (silent mode)...")
        has_update = ota_updater.check_for_updates(silent=True)
        print(f"Update available: {has_update}")
        
        print("✓ OTA updater functionality test passed")
        return True
    except Exception as e:
        print(f"✗ OTA updater functionality test failed: {e}")
        return False

def test_gui_components():
    """测试GUI组件"""
    print("\nTesting GUI components...")
    try:
        from ota.gui.dialog import UpdateDialog, UpdateNotificationDialog
        print("✓ GUI components imported successfully")
        return True
    except Exception as e:
        print(f"✗ GUI components import failed: {e}")
        return False

def test_platform_updaters():
    """测试平台更新器"""
    print("\nTesting platform updaters...")
    try:
        from ota.core.platforms import SparkleUpdater, WinSparkleUpdater, GenericUpdater
        print("✓ Platform updaters imported successfully")
        return True
    except Exception as e:
        print(f"✗ Platform updaters import failed: {e}")
        return False

def test_build_tools():
    """测试构建工具"""
    print("\nTesting build tools...")
    try:
        from ota.build import SparkleBuilder
        print("✓ Build tools imported successfully")
        return True
    except Exception as e:
        print(f"✗ Build tools import failed: {e}")
        return False

def test_server():
    """测试更新服务器"""
    print("\nTesting update server...")
    try:
        from ota.server import update_server_app
        print("✓ Update server imported successfully")
        return True
    except Exception as e:
        print(f"✗ Update server import failed: {e}")
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
        test_build_tools,
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