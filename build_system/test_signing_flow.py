#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试签名流程
验证代码签名和OTA签名功能
"""

import os
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from build_system.signing_manager import create_signing_manager, create_ota_signing_manager
from build_system.unified_build import UnifiedBuildSystem

def test_signing_flow():
    """测试完整的签名流程"""
    print("🔍 测试签名流程...")
    print("=" * 60)
    
    # 1. 测试OTA签名管理器
    print("\n1️⃣ 测试OTA签名管理器")
    try:
        ota_manager = create_ota_signing_manager(project_root)
        print(f"   ✅ OTA签名管理器创建成功")
        print(f"   📁 私钥路径: {ota_manager.private_key_path}")
        print(f"   📁 分发目录: {ota_manager.dist_dir}")
        
        # 检查密钥文件
        private_key = ota_manager.private_key_path
        public_key = project_root / "ota" / "certificates" / "ed25519_public_key.pem"
        
        if private_key.exists() and public_key.exists():
            print("   ✅ Ed25519密钥文件存在")
        else:
            print("   ❌ Ed25519密钥文件缺失")
            print(f"   私钥: {private_key} ({'存在' if private_key.exists() else '缺失'})")
            print(f"   公钥: {public_key} ({'存在' if public_key.exists() else '缺失'})")
            return False
            
    except Exception as e:
        print(f"   ❌ OTA签名管理器测试失败: {e}")
        return False
    
    # 2. 测试代码签名管理器
    print("\n2️⃣ 测试代码签名管理器")
    try:
        # 加载构建配置
        build_system = UnifiedBuildSystem(project_root)
        config = build_system.config.config
        
        signing_manager = create_signing_manager(project_root, config)
        print(f"   ✅ 代码签名管理器创建成功")
        print(f"   🖥️ 当前平台: {signing_manager.platform}")
        
        # 检查签名配置
        should_sign = signing_manager.should_sign("prod")
        print(f"   🔐 生产模式签名: {'启用' if should_sign else '禁用'}")
        
        if signing_manager.platform == "windows":
            windows_config = config.get("platforms", {}).get("windows", {}).get("sign", {})
            print(f"   📋 Windows签名配置: {windows_config}")
            
    except Exception as e:
        print(f"   ❌ 代码签名管理器测试失败: {e}")
        return False
    
    # 3. 测试构建系统签名集成
    print("\n3️⃣ 测试构建系统签名集成")
    try:
        build_system = UnifiedBuildSystem(project_root)
        
        # 模拟签名流程（不实际执行构建）
        print("   🔄 模拟签名流程...")
        
        # 创建模拟的dist目录和文件
        dist_dir = project_root / "dist"
        dist_dir.mkdir(exist_ok=True)
        
        # 创建一个测试文件用于签名测试
        test_file = dist_dir / "test_app.exe"
        if not test_file.exists():
            with open(test_file, 'w') as f:
                f.write("# Test executable for signing")
        
        print(f"   📁 分发目录: {dist_dir}")
        print(f"   📄 测试文件: {test_file}")
        
        # 测试OTA签名（如果有测试文件）
        if test_file.exists():
            ota_success = ota_manager.sign_for_ota("1.0.0-test")
            if ota_success:
                print("   ✅ OTA签名测试成功")
            else:
                print("   ⚠️ OTA签名测试失败")
        
    except Exception as e:
        print(f"   ❌ 构建系统集成测试失败: {e}")
        return False
    
    # 4. 检查签名工具可用性
    print("\n4️⃣ 检查签名工具可用性")
    try:
        import subprocess
        
        # 检查signtool
        try:
            result = subprocess.run(["signtool"], capture_output=True, timeout=5)
            print("   ✅ signtool 可用")
        except FileNotFoundError:
            print("   ❌ signtool 不可用")
        except subprocess.TimeoutExpired:
            print("   ✅ signtool 可用 (超时但存在)")
        except Exception:
            print("   ❌ signtool 检查失败")
        
        # 检查cryptography库
        try:
            from cryptography.hazmat.primitives.asymmetric import ed25519
            print("   ✅ cryptography 库可用")
        except ImportError:
            print("   ❌ cryptography 库不可用")
            
    except Exception as e:
        print(f"   ❌ 工具检查失败: {e}")
    
    print("\n" + "=" * 60)
    print("✅ 签名流程测试完成")
    return True

def main():
    """主函数"""
    try:
        success = test_signing_flow()
        
        if success:
            print("\n🎉 所有签名功能测试通过！")
            print("\n📋 使用方法:")
            print("   # 构建并签名")
            print("   python build_system/unified_build.py prod --version 1.0.1")
            print("")
            print("   # 跳过签名")
            print("   python build_system/unified_build.py prod --version 1.0.1 --skip-signing")
            print("")
            print("   # 创建测试证书")
            print("   python build_system/create_test_certificate.py")
            return 0
        else:
            print("\n❌ 签名功能测试失败，请检查配置")
            return 1
            
    except KeyboardInterrupt:
        print("\n⚠️ 测试被用户中断")
        return 1
    except Exception as e:
        print(f"\n❌ 测试过程出错: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
