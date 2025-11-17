#!/usr/bin/env python3
"""
本地 OTA 验证工具 - 完整的开发验证框架
支持快速测试、诊断和调试 OTA 功能
"""

import os
import sys
import json
import time
import requests
from pathlib import Path
from typing import Dict, List, Tuple

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

os.environ['ECBOT_DEV_MODE'] = '1'

from ota.core.updater import OTAUpdater
from ota.core.config import ota_config
from utils.logger_helper import logger_helper as logger


class OTAValidator:
    """OTA 本地验证工具"""
    
    def __init__(self, server_url: str = "http://127.0.0.1:8080"):
        self.server_url = server_url
        self.results = {
            "server_health": None,
            "config": None,
            "updater": None,
            "update_check": None,
            "api_endpoints": {}
        }
    
    def print_header(self, title: str):
        """打印标题"""
        print(f"\n{'='*70}")
        print(f"  {title}")
        print(f"{'='*70}\n")
    
    def print_section(self, title: str):
        """打印小节标题"""
        print(f"\n{title}")
        print(f"{'-'*70}")
    
    def check_server_health(self) -> bool:
        """检查服务器健康状态"""
        self.print_section("🏥 服务器健康检查")
        
        try:
            response = requests.get(f"{self.server_url}/health", timeout=5)
            if response.status_code == 200:
                print(f"✅ 服务器运行正常")
                self.results["server_health"] = True
                return True
            else:
                print(f"❌ 服务器返回错误状态: {response.status_code}")
                self.results["server_health"] = False
                return False
        except requests.exceptions.ConnectionError:
            print(f"❌ 无法连接到服务器: {self.server_url}")
            print(f"   请确保服务器正在运行: python ota/server/update_server.py")
            self.results["server_health"] = False
            return False
        except Exception as e:
            print(f"❌ 检查失败: {e}")
            self.results["server_health"] = False
            return False
    
    def check_config(self) -> bool:
        """检查配置"""
        self.print_section("⚙️  配置检查")
        
        try:
            config_info = {
                "dev_mode": ota_config.is_dev_mode(),
                "use_local_server": ota_config.is_using_local_server(),
                "update_server": ota_config.get_update_server(),
                "allow_http": ota_config.is_http_allowed(),
                "signature_verification": ota_config.is_signature_verification_enabled(),
                "check_interval": ota_config.get_check_interval()
            }
            
            for key, value in config_info.items():
                status = "✅" if value else "⚠️ "
                print(f"{status} {key}: {value}")
            
            self.results["config"] = config_info
            return True
        except Exception as e:
            print(f"❌ 配置检查失败: {e}")
            return False
    
    def check_updater(self) -> bool:
        """检查更新器"""
        self.print_section("🚀 更新器检查")
        
        try:
            updater = OTAUpdater()
            status = updater.get_status()
            
            print(f"✅ 平台: {status['platform']}")
            print(f"✅ 当前版本: {status['app_version']}")
            print(f"✅ 更新器类型: {type(updater.platform_updater).__name__}")
            
            self.results["updater"] = {
                "platform": status['platform'],
                "version": status['app_version'],
                "updater_type": type(updater.platform_updater).__name__
            }
            return True
        except Exception as e:
            print(f"❌ 更新器检查失败: {e}")
            return False
    
    def test_api_endpoints(self) -> Dict[str, bool]:
        """测试 API 端点"""
        self.print_section("🔌 API 端点测试")
        
        endpoints = {
            "/health": "健康检查",
            "/api/check?version=1.0.0&platform=darwin": "检查更新",
            "/appcast.xml": "Appcast 文件",
            "/admin/signatures": "签名列表"
        }
        
        results = {}
        for endpoint, description in endpoints.items():
            try:
                url = f"{self.server_url}{endpoint}"
                response = requests.get(url, timeout=5)
                status = "✅" if response.status_code == 200 else "⚠️ "
                print(f"{status} {endpoint} ({description}): {response.status_code}")
                results[endpoint] = response.status_code == 200
            except Exception as e:
                print(f"❌ {endpoint}: {e}")
                results[endpoint] = False
        
        self.results["api_endpoints"] = results
        return results
    
    def check_for_updates(self) -> bool:
        """检查更新"""
        self.print_section("🔍 更新检查")
        
        try:
            ota_config.set_use_local_server(True)
            ota_config.set_local_server_url(self.server_url)
            
            updater = OTAUpdater()
            has_update, update_info = updater.check_for_updates(return_info=True)
            
            if has_update:
                print(f"✅ 发现新版本!")
                print(f"   当前版本: {updater.app_version}")
                print(f"   最新版本: {update_info.get('latest_version', 'N/A')}")
                print(f"   描述: {update_info.get('description', 'N/A')}")
            else:
                print(f"ℹ️  当前已是最新版本")
                if isinstance(update_info, dict):
                    print(f"   最新版本: {update_info.get('latest_version', 'N/A')}")
            
            self.results["update_check"] = {
                "has_update": has_update,
                "info": str(update_info)
            }
            return True
        except Exception as e:
            print(f"❌ 更新检查失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def generate_report(self) -> str:
        """生成验证报告"""
        self.print_header("📊 验证报告")
        
        report = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "server_url": self.server_url,
            "results": self.results
        }
        
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return json.dumps(report, indent=2, ensure_ascii=False)
    
    def run_full_validation(self) -> bool:
        """运行完整验证"""
        self.print_header("🔧 eCan.ai OTA 本地验证工具")
        
        checks = [
            ("服务器健康检查", self.check_server_health),
            ("配置检查", self.check_config),
            ("更新器检查", self.check_updater),
            ("API 端点测试", lambda: bool(self.test_api_endpoints())),
            ("更新检查", self.check_for_updates)
        ]
        
        results = []
        for name, check_func in checks:
            try:
                result = check_func()
                results.append((name, result))
            except Exception as e:
                print(f"❌ {name} 异常: {e}")
                results.append((name, False))
        
        # 生成总结
        self.print_header("✅ 验证总结")
        passed = sum(1 for _, result in results if result)
        total = len(results)
        
        for name, result in results:
            status = "✅" if result else "❌"
            print(f"{status} {name}")
        
        print(f"\n总体: {passed}/{total} 检查通过")
        
        return passed == total


def main():
    """主函数"""
    validator = OTAValidator()
    success = validator.run_full_validation()
    validator.generate_report()
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())

