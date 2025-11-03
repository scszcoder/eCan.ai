#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
创建测试用的代码签名证书
仅用于开发和测试环境
"""

import os
import subprocess
from pathlib import Path

def create_test_certificate(project_root: Path = None):
    """创建测试用的自签名证书"""
    project_root = project_root or Path.cwd()
    cert_dir = project_root / "build_system" / "certificates"
    cert_dir.mkdir(exist_ok=True)
    
    cert_file = cert_dir / "test_certificate.pfx"
    
    if cert_file.exists():
        print(f"[CERT] 测试证书已存在: {cert_file}")
        return True
    
    print("[CERT] 创建测试用自签名证书...")
    
    try:
        # 使用PowerShell创建自签名证书
        ps_script = f'''
$cert = New-SelfSignedCertificate -Type CodeSigning -Subject "CN=eCan Test Certificate" `
    -KeyAlgorithm RSA -KeyLength 2048 `
    -Provider "Microsoft Enhanced RSA and AES Cryptographic Provider" `
    -KeyExportPolicy Exportable -KeyUsage DigitalSignature `
    -CertStoreLocation Cert:\\CurrentUser\\My

$password = ConvertTo-SecureString -String "test123" -Force -AsPlainText
Export-PfxCertificate -Cert $cert -FilePath "{cert_file}" -Password $password
'''
        
        result = subprocess.run(
            ["powershell", "-Command", ps_script],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode == 0 and cert_file.exists():
            print(f"[CERT] [OK] 测试证书创建成功: {cert_file}")
            print("[CERT] 💡 证书密码: test123")
            print("[CERT] 💡 设置环境变量: $env:CERT_PASSWORD = 'test123'")
            return True
        else:
            print(f"[CERT] [ERROR] 证书创建失败: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"[CERT] [ERROR] 证书创建异常: {e}")
        return False

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="创建测试用代码签名证书")
    parser.add_argument("--project-root", help="项目根目录路径")
    
    args = parser.parse_args()
    
    project_root = Path(args.project_root) if args.project_root else Path.cwd()
    
    success = create_test_certificate(project_root)
    return 0 if success else 1

if __name__ == "__main__":
    import sys
    sys.exit(main())
