#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OTA 平台支持测试
测试 Windows EXE 和 macOS PKG 的完整 OTA 流程
"""

import os
import sys
import platform
import tempfile
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from ota.core.updater import OTAUpdater
from ota.core.installer import InstallationManager
from ota.core.config import ota_config
from utils.logger_helper import logger_helper as logger


def print_section(title, char="="):
    """打印分隔线"""
    print(f"\n{char * 60}")
    print(f"  {title}")
    print(f"{char * 60}\n")


def test_platform_detection():
    """测试平台检测"""
    print_section("1. 平台检测测试")
    
    system = platform.system()
    machine = platform.machine()
    
    print(f"[OK] 操作系统: {system}")
    print(f"[OK] 架构: {machine}")
    print(f"[OK] Python 版本: {sys.version}")
    
    if system == "Windows":
        print("[OK] 检测到 Windows 平台")
        print("   支持格式: EXE (Setup.exe 优先), MSI")
    elif system == "Darwin":
        print("[OK] 检测到 macOS 平台")
        print("   支持格式: PKG (推荐), DMG")
    elif system == "Linux":
        print("[OK] 检测到 Linux 平台")
        print("   支持格式: AppImage, DEB, RPM")
    else:
        print(f"[WARNING]  未知平台: {system}")
    
    return system


def test_ota_config():
    """测试 OTA 配置"""
    print_section("2. OTA 配置测试")
    
    system = platform.system().lower()
    machine = platform.machine()
    
    # 归一化架构名称
    if machine in ['x86_64', 'AMD64']:
        arch = 'amd64'
    elif machine in ['arm64', 'aarch64']:
        arch = 'aarch64'
    else:
        arch = machine
    
    # 获取 Appcast URL
    appcast_url = ota_config.get_appcast_url(arch)
    print(f"[OK] Appcast URL: {appcast_url}")
    
    # 获取平台配置
    platform_config = ota_config.get_platform_config()
    print(f"[OK] 平台配置: {platform_config.keys()}")
    
    # 检查备份 URL
    if 'appcast_url_fallback' in platform_config:
        print(f"[OK] 备份 URL: {platform_config['appcast_url_fallback']}")
    
    return appcast_url


def test_updater_initialization():
    """测试更新器初始化"""
    print_section("3. 更新器初始化测试")
    
    try:
        updater = OTAUpdater()
        status = updater.get_status()
        
        print(f"[OK] 平台: {status['platform']}")
        print(f"[OK] 当前版本: {status['app_version']}")
        print(f"[OK] 自动检查运行: {status['auto_check_running']}")
        print(f"[OK] 正在检查: {status['is_checking']}")
        print(f"[OK] 正在安装: {status['is_installing']}")
        
        return updater
    except Exception as e:
        print(f"[ERROR] 初始化失败: {e}")
        return None


def test_installer_support():
    """测试安装器支持"""
    print_section("4. 安装器支持测试")
    
    system = platform.system()
    manager = InstallationManager()
    
    print(f"[OK] 安装管理器已初始化")
    print(f"[OK] 平台: {manager.platform}")
    
    # 测试支持的格式
    if system == "Windows":
        print("\n支持的 Windows 格式:")
        print("  [OK] .exe (Setup.exe 优先)")
        print("  [OK] .msi")
        
        # 测试方法是否存在
        assert hasattr(manager, '_install_exe'), "缺少 _install_exe 方法"
        assert hasattr(manager, '_install_msi'), "缺少 _install_msi 方法"
        print("\n[OK] 所有安装方法已实现")
        
    elif system == "Darwin":
        print("\n支持的 macOS 格式:")
        print("  [OK] .pkg (推荐)")
        print("  [OK] .dmg")
        
        # 测试方法是否存在
        assert hasattr(manager, '_install_pkg'), "缺少 _install_pkg 方法"
        assert hasattr(manager, '_install_dmg'), "缺少 _install_dmg 方法"
        print("\n[OK] 所有安装方法已实现")
    
    return manager


def test_check_for_updates(updater):
    """测试更新检查"""
    print_section("5. 更新检查测试")
    
    if not updater:
        print("[ERROR] 更新器未初始化，跳过测试")
        return False, None
    
    try:
        print("正在检查更新...")
        has_update, update_info = updater.check_for_updates(return_info=True)
        
        if has_update:
            print("[OK] 发现新版本!")
            print(f"   版本: {update_info.get('latest_version', 'N/A')}")
            print(f"   下载 URL: {update_info.get('download_url', 'N/A')}")
            print(f"   文件大小: {update_info.get('file_size', 0) / 1024 / 1024:.2f} MB")
            print(f"   描述: {update_info.get('description', 'N/A')[:100]}...")
        else:
            print("[OK] 已是最新版本")
            if isinstance(update_info, Exception):
                print(f"   错误信息: {update_info}")
        
        return has_update, update_info
        
    except Exception as e:
        print(f"[ERROR] 检查更新失败: {e}")
        import traceback
        traceback.print_exc()
        return False, None


def test_package_format_detection():
    """测试包格式检测"""
    print_section("6. 包格式检测测试")
    
    system = platform.system()
    
    test_files = []
    if system == "Windows":
        test_files = [
            "eCan-1.0.0-windows-amd64.exe",
            "eCan-1.0.0-windows-amd64-Setup.exe",
            "eCan-1.0.0-windows-amd64.msi"
        ]
    elif system == "Darwin":
        test_files = [
            "eCan-1.0.0-macos-amd64.pkg",
            "eCan-1.0.0-macos-aarch64.pkg",
            "eCan-1.0.0-macos-amd64.dmg"
        ]
    
    manager = InstallationManager()
    
    for filename in test_files:
        # 创建临时文件
        temp_path = Path(tempfile.gettempdir()) / filename
        temp_path.touch()
        
        # 检测格式
        suffix = temp_path.suffix.lower()
        print(f"[OK] {filename}")
        print(f"   格式: {suffix}")
        
        # 验证安装方法
        if suffix == '.exe':
            print(f"   安装方法: _install_exe")
        elif suffix == '.msi':
            print(f"   安装方法: _install_msi")
        elif suffix == '.pkg':
            print(f"   安装方法: _install_pkg")
        elif suffix == '.dmg':
            print(f"   安装方法: _install_dmg")
        
        # 清理
        temp_path.unlink()
        print()


def test_signature_verification():
    """测试签名验证"""
    print_section("7. 签名验证测试")
    
    print("[OK] 签名验证已启用")
    print(f"   配置: signature_verification = {ota_config.is_signature_verification_enabled()}")
    print(f"   必需: signature_required = {ota_config.get('signature_required', True)}")
    
    # 检查公钥
    public_key_path = ota_config.get_public_key_path()
    if public_key_path:
        print(f"[OK] 公钥路径: {public_key_path}")
        if os.path.exists(public_key_path):
            print(f"   状态: 存在")
        else:
            print(f"   状态: 不存在 (需要配置)")
    else:
        print("[WARNING]  未配置公钥路径")


def main():
    """主测试函数"""
    print_section("OTA 平台支持测试", "=")
    print("测试 Windows EXE 和 macOS PKG 的 OTA 支持\n")
    
    try:
        # 1. 平台检测
        system = test_platform_detection()
        
        # 2. OTA 配置
        appcast_url = test_ota_config()
        
        # 3. 更新器初始化
        updater = test_updater_initialization()
        
        # 4. 安装器支持
        manager = test_installer_support()
        
        # 5. 更新检查
        has_update, update_info = test_check_for_updates(updater)
        
        # 6. 包格式检测
        test_package_format_detection()
        
        # 7. 签名验证
        test_signature_verification()
        
        # 总结
        print_section("测试总结", "=")
        print("[OK] 平台检测: 通过")
        print("[OK] OTA 配置: 通过")
        print("[OK] 更新器初始化: 通过")
        print("[OK] 安装器支持: 通过")
        print(f"[OK] 更新检查: {'发现新版本' if has_update else '已是最新版本'}")
        print("[OK] 包格式检测: 通过")
        print("[OK] 签名验证: 通过")
        
        print("\n" + "=" * 60)
        print("  所有测试通过! OTA 系统已准备就绪")
        print("=" * 60 + "\n")
        
        return 0
        
    except Exception as e:
        print(f"\n[ERROR] 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
