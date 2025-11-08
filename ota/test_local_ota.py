#!/usr/bin/env python3
"""
eCan.ai OTA 功能本地测试脚本
用于快速测试本地 OTA 更新功能
"""

import os
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径（当前文件在 ota 目录下）
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 设置开发模式
os.environ['ECBOT_DEV_MODE'] = '1'

from ota.core.updater import OTAUpdater
from ota.core.config import ota_config
from utils.logger_helper import logger_helper as logger


def print_section(title: str, char: str = "="):
    """打印章节标题"""
    print(f"\n{char * 60}")
    print(f"{title}")
    print(f"{char * 60}")


def test_configuration():
    """测试配置"""
    print_section("📋 第一步：配置本地 OTA 服务器")
    
    # 配置本地服务器
    ota_config.set_use_local_server(True)
    ota_config.set_local_server_url("http://127.0.0.1:8080")
    
    # 显示配置信息
    update_server = ota_config.get_update_server()
    print(f"✅ 更新服务器: {update_server}")
    print(f"✅ 开发模式: {ota_config.is_dev_mode()}")
    print(f"✅ 本地服务器: {ota_config.is_using_local_server()}")
    print(f"✅ 允许 HTTP: {ota_config.is_http_allowed()}")
    print(f"✅ 签名验证: {ota_config.is_signature_verification_enabled()}")
    
    # 获取平台配置
    platform_config = ota_config.get_platform_config()
    print(f"✅ 平台配置: {list(platform_config.keys())}")
    
    return True


def test_updater_initialization():
    """测试更新器初始化"""
    print_section("🚀 第二步：初始化 OTA 更新器")
    
    try:
        updater = OTAUpdater()
        status = updater.get_status()
        
        print(f"✅ 平台: {status['platform']}")
        print(f"✅ 当前版本: {status['app_version']}")
        print(f"✅ 更新器类型: {type(updater.platform_updater).__name__}")
        print(f"✅ 正在检查: {status['is_checking']}")
        print(f"✅ 正在安装: {status['is_installing']}")
        print(f"✅ 自动检查运行中: {status['auto_check_running']}")
        
        return updater
    except Exception as e:
        print(f"❌ 更新器初始化失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_check_for_updates(updater: OTAUpdater):
    """测试更新检查"""
    print_section("🔍 第三步：检查更新")
    
    print("正在连接到更新服务器...")
    print("提示: 确保本地服务器正在运行 (python ota/server/update_server.py)")
    print()
    
    try:
        has_update, update_info = updater.check_for_updates(return_info=True)
        
        if has_update:
            print("✅ 发现新版本!")
            print(f"   当前版本: {updater.app_version}")
            print(f"   最新版本: {update_info.get('latest_version', 'N/A')}")
            print(f"   更新描述: {update_info.get('description', 'N/A')}")
            print(f"   发布日期: {update_info.get('release_date', 'N/A')}")
            print(f"   下载地址: {update_info.get('download_url', 'N/A')}")
            print(f"   文件大小: {update_info.get('file_size', 0)} bytes")
            print(f"   签名信息: {update_info.get('signature', 'N/A')}")
        else:
            print("ℹ️  当前已是最新版本")
            if update_info:
                # 检查是否是错误对象
                from ota.core.errors import UpdateError
                if isinstance(update_info, UpdateError):
                    print(f"   错误代码: {update_info.code}")
                    print(f"   错误信息: {update_info.message}")
                    if update_info.details:
                        print(f"   详细信息: {update_info.details}")
                else:
                    print(f"   最新版本: {update_info.get('latest_version', 'N/A')}")
        
        return has_update
        
    except Exception as e:
        print(f"❌ 更新检查失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_server_connection():
    """测试服务器连接"""
    print_section("🌐 附加测试：服务器连接测试")
    
    try:
        import requests
        
        server_url = "http://127.0.0.1:8080"
        
        # 测试 API 端点
        endpoints = [
            "/api/check?version=1.0.0&platform=darwin",
            "/appcast.xml",
            "/admin/signatures"
        ]
        
        for endpoint in endpoints:
            url = server_url + endpoint
            try:
                response = requests.get(url, timeout=5)
                status = "✅" if response.status_code == 200 else "⚠️"
                print(f"{status} {endpoint} - Status: {response.status_code}")
            except requests.exceptions.ConnectionError:
                print(f"❌ {endpoint} - 连接失败 (服务器未运行?)")
            except Exception as e:
                print(f"❌ {endpoint} - 错误: {e}")
        
    except ImportError:
        print("⚠️  requests 库未安装，跳过连接测试")
        print("   安装: pip install requests")


def test_configuration_file():
    """测试配置文件"""
    print_section("📄 配置文件信息")
    
    config_path = ota_config.config_file
    print(f"配置文件路径: {config_path}")
    print(f"配置文件存在: {config_path.exists()}")
    
    if config_path.exists():
        import json
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            print("\n当前配置:")
            for key, value in config_data.items():
                if isinstance(value, dict):
                    print(f"  {key}:")
                    for sub_key, sub_value in value.items():
                        print(f"    {sub_key}: {sub_value}")
                else:
                    print(f"  {key}: {value}")
        except Exception as e:
            print(f"读取配置文件失败: {e}")


def main():
    """主测试函数"""
    print("\n" + "=" * 60)
    print("  eCan.ai OTA 功能本地测试")
    print("=" * 60)
    print("此脚本将测试本地 OTA 更新功能")
    print("请确保本地服务器正在运行:")
    print("  python ota/server/update_server.py")
    print("=" * 60)
    
    try:
        # 1. 测试配置
        if not test_configuration():
            print("\n❌ 配置测试失败")
            return 1
        
        # 2. 测试配置文件
        test_configuration_file()
        
        # 3. 测试服务器连接
        test_server_connection()
        
        # 4. 初始化更新器
        updater = test_updater_initialization()
        if not updater:
            print("\n❌ 更新器初始化失败")
            return 1
        
        # 5. 检查更新
        has_update = test_check_for_updates(updater)
        
        # 6. 总结
        print_section("✅ 测试完成!", "=")
        print("\n测试总结:")
        print(f"  配置: ✅")
        print(f"  更新器初始化: ✅")
        print(f"  更新检查: {'✅ 发现更新' if has_update else 'ℹ️  无更新'}")
        
        print("\n下一步操作:")
        if has_update:
            print("  1. 可以尝试安装更新（需要真实的安装包）")
            print("  2. 检查 appcast.xml 的生成")
        else:
            print("  1. 修改服务器配置中的版本号")
            print("  2. 重新生成 appcast.xml")
            print("  3. 再次运行此测试")
        
        print("\n相关命令:")
        print("  启动服务器: python ota/server/update_server.py")
        print("  查看 appcast: curl http://127.0.0.1:8080/appcast.xml")
        print("  检查更新 API: curl 'http://127.0.0.1:8080/api/check?version=1.0.0'")
        print()
        
        return 0
        
    except KeyboardInterrupt:
        print("\n\n⚠️  测试被用户中断")
        return 130
    except Exception as e:
        print(f"\n\n❌ 测试过程中出现异常: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
