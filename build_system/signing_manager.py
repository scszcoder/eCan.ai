#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ECBot构建系统签名管理器
集成代码签名和OTA签名到构建流程中
"""

import os
import json
import subprocess
import platform
from pathlib import Path
from typing import Dict, Any, Optional

class SigningManager:
    """代码签名管理器"""
    
    def __init__(self, project_root: Path = None, config: Dict[str, Any] = None):
        self.project_root = project_root or Path.cwd()
        self.config = config or {}
        self.platform = platform.system().lower()
        self.dist_dir = self.project_root / "dist"
        
    def should_sign(self, mode: str = "prod") -> bool:
        """判断是否应该进行签名"""
        # 开发模式通常跳过签名以加快构建速度
        if mode == "dev":
            return False
        
        # 检查平台配置
        platform_config = self.config.get("platforms", {})
        
        if self.platform == "windows":
            return platform_config.get("windows", {}).get("sign", {}).get("enabled", False)
        elif self.platform == "darwin":
            return platform_config.get("macos", {}).get("codesign", {}).get("enabled", False)
        
        return False
    
    def sign_artifacts(self, mode: str = "prod") -> bool:
        """签名构建产物"""
        if not self.should_sign(mode):
            print("[SIGN] 签名已禁用或不支持当前平台")
            return True
        
        print(f"[SIGN] 开始签名构建产物 (模式: {mode})")
        
        try:
            if self.platform == "windows":
                return self._sign_windows_artifacts()
            elif self.platform == "darwin":
                return self._sign_macos_artifacts()
            else:
                print(f"[SIGN] 不支持的平台: {self.platform}")
                return True
                
        except Exception as e:
            print(f"[SIGN] 签名过程出错: {e}")
            # 签名失败不应该阻止构建，只是警告
            return True
    
    def _sign_windows_artifacts(self) -> bool:
        """签名Windows构建产物"""
        print("[SIGN] 执行Windows代码签名...")
        
        config = self.config.get("platforms", {}).get("windows", {}).get("sign", {})
        signtool = config.get("tool", "signtool")
        
        if not self._check_tool_available(signtool):
            print(f"[SIGN] 警告: {signtool} 不可用，跳过签名")
            return True
        
        # 查找需要签名的文件
        files_to_sign = list(self.dist_dir.rglob("*.exe")) + list(self.dist_dir.rglob("*.dll"))
        
        if not files_to_sign:
            print("[SIGN] 未找到需要签名的Windows文件")
            return True
        
        # 签名文件
        success_count = sum(1 for f in files_to_sign if self._sign_windows_file(f, config))
        print(f"[SIGN] Windows签名完成: {success_count}/{len(files_to_sign)} 个文件")
        return success_count > 0
    
    def _sign_windows_file(self, file_path: Path, config: Dict[str, Any]) -> bool:
        """签名单个Windows文件"""
        try:
            # 构建签名命令
            cmd = [
                config.get("tool", "signtool"), "sign",
                "/f", config.get("certificate", ""),
                "/fd", "SHA256",
                "/tr", "http://timestamp.digicert.com",
                "/td", "SHA256",
                str(file_path)
            ]
            
            # 添加密码（如果有）
            password = config.get("password", "")
            if password:
                cmd.insert(-1, "/p")
                cmd.insert(-1, password)
            
            # 过滤空参数
            cmd = [arg for arg in cmd if arg]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            if result.returncode == 0:
                print(f"[SIGN] ✅ 已签名: {file_path.name}")
                return True
            else:
                print(f"[SIGN] ❌ 签名失败: {file_path.name} - {result.stderr.strip()}")
                return False
                
        except Exception as e:
            print(f"[SIGN] ❌ 签名异常: {file_path.name} - {e}")
            return False
    
    def _sign_macos_artifacts(self) -> bool:
        """签名macOS构建产物"""
        print("[SIGN] 执行macOS代码签名...")
        
        config = self.config.get("platforms", {}).get("macos", {}).get("codesign", {})
        
        if not self._check_tool_available("codesign"):
            print("[SIGN] 警告: codesign 不可用，跳过签名")
            return True
        
        # 查找需要签名的文件
        files_to_sign = list(self.dist_dir.rglob("*.app")) + list(self.dist_dir.rglob("*.dylib"))
        
        if not files_to_sign:
            print("[SIGN] 未找到需要签名的macOS文件")
            return True
        
        # 签名文件
        success_count = sum(1 for f in files_to_sign if self._sign_macos_file(f, config))
        print(f"[SIGN] macOS签名完成: {success_count}/{len(files_to_sign)} 个文件")
        return success_count > 0
    
    def _sign_macos_file(self, file_path: Path, config: Dict[str, Any]) -> bool:
        """签名单个macOS文件"""
        try:
            identity = config.get("identity", "")
            if not identity:
                print(f"[SIGN] 警告: 未配置签名身份")
                return False
            
            cmd = ["codesign", "--sign", identity, "--force", "--timestamp", str(file_path)]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            if result.returncode == 0:
                print(f"[SIGN] ✅ 已签名: {file_path.name}")
                return True
            else:
                print(f"[SIGN] ❌ 签名失败: {file_path.name} - {result.stderr.strip()}")
                return False
                
        except Exception as e:
            print(f"[SIGN] ❌ 签名异常: {file_path.name} - {e}")
            return False
    
    def _check_tool_available(self, tool: str) -> bool:
        """检查签名工具是否可用"""
        try:
            result = subprocess.run(
                [tool], 
                capture_output=True, 
                text=True, 
                timeout=5
            )
            return True
        except FileNotFoundError:
            return False
        except subprocess.TimeoutExpired:
            return True  # 工具存在但可能在等待参数
        except Exception:
            return False
    
    def verify_signatures(self) -> bool:
        """验证签名"""
        print("[VERIFY] 验证构建产物签名...")
        
        try:
            if self.platform == "windows":
                return self._verify_windows_signatures()
            elif self.platform == "darwin":
                return self._verify_macos_signatures()
            else:
                print(f"[VERIFY] 当前平台 {self.platform} 不需要验证")
                return True
        except Exception as e:
            print(f"[VERIFY] 验证过程出错: {e}")
            return True
    
    def _verify_windows_signatures(self) -> bool:
        """验证Windows签名"""
        if not self._check_tool_available("signtool"):
            print("[VERIFY] signtool 不可用，跳过验证")
            return True
        
        signed_files = list(self.dist_dir.rglob("*.exe")) + list(self.dist_dir.rglob("*.dll"))
        
        if not signed_files:
            print("[VERIFY] 未找到需要验证的文件")
            return True
        
        verified_count = 0
        for file_path in signed_files:
            try:
                result = subprocess.run(
                    ["signtool", "verify", "/pa", str(file_path)],
                    capture_output=True, text=True, timeout=30
                )
                
                if result.returncode == 0:
                    print(f"[VERIFY] ✅ 签名有效: {file_path.name}")
                    verified_count += 1
                else:
                    print(f"[VERIFY] ❌ 签名无效: {file_path.name}")
            except Exception as e:
                print(f"[VERIFY] ❌ 验证失败: {file_path.name} - {e}")
        
        print(f"[VERIFY] Windows签名验证: {verified_count}/{len(signed_files)} 个文件")
        return verified_count > 0
    
    def _verify_macos_signatures(self) -> bool:
        """验证macOS签名"""
        if not self._check_tool_available("codesign"):
            print("[VERIFY] codesign 不可用，跳过验证")
            return True
        
        signed_files = list(self.dist_dir.rglob("*.app")) + list(self.dist_dir.rglob("*.dylib"))
        
        if not signed_files:
            print("[VERIFY] 未找到需要验证的文件")
            return True
        
        verified_count = 0
        for file_path in signed_files:
            try:
                result = subprocess.run(
                    ["codesign", "--verify", str(file_path)],
                    capture_output=True, text=True, timeout=30
                )
                
                if result.returncode == 0:
                    print(f"[VERIFY] ✅ 签名有效: {file_path.name}")
                    verified_count += 1
                else:
                    print(f"[VERIFY] ❌ 签名无效: {file_path.name}")
            except Exception as e:
                print(f"[VERIFY] ❌ 验证失败: {file_path.name} - {e}")
        
        print(f"[VERIFY] macOS签名验证: {verified_count}/{len(signed_files)} 个文件")
        return verified_count > 0

class OTASigningManager:
    """OTA签名管理器 - 使用Ed25519签名算法"""
    
    def __init__(self, project_root: Path = None):
        self.project_root = project_root or Path.cwd()
        self.private_key_path = self.project_root / "build_system" / "certificates" / "ed25519_private_key.pem"
        self.dist_dir = self.project_root / "dist"
    
    def sign_for_ota(self, version: str) -> bool:
        """为OTA分发签名构建产物"""
        print(f"[OTA-SIGN] 为OTA分发签名构建产物 (版本: {version})")
        
        try:
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.asymmetric import ed25519
            import base64
            
            # 加载私钥
            if not self.private_key_path.exists():
                print(f"[OTA-SIGN] ❌ Ed25519私钥文件不存在: {self.private_key_path}")
                return False
            
            with open(self.private_key_path, 'rb') as f:
                private_key = serialization.load_pem_private_key(f.read(), password=None)
            
            if not isinstance(private_key, ed25519.Ed25519PrivateKey):
                print("[OTA-SIGN] ❌ 私钥格式不正确")
                return False
            
            # 查找需要签名的分发文件
            artifacts = list(self.dist_dir.glob("*.exe")) + list(self.dist_dir.glob("*.dmg")) + list(self.dist_dir.glob("*.pkg"))
            
            if not artifacts:
                print("[OTA-SIGN] ❌ 未找到需要签名的分发文件")
                return False
            
            signatures = {}
            
            # 签名每个文件
            for artifact in artifacts:
                print(f"[OTA-SIGN] 正在签名: {artifact.name}")
                
                try:
                    # 读取文件内容
                    with open(artifact, 'rb') as f:
                        file_data = f.read()
                    
                    # 生成Ed25519签名
                    signature = private_key.sign(file_data)
                    signature_b64 = base64.b64encode(signature).decode('ascii')
                    
                    signatures[artifact.name] = {
                        "signature": signature_b64,
                        "algorithm": "Ed25519",
                        "file_size": len(file_data)
                    }
                    
                    print(f"[OTA-SIGN] ✅ 已签名: {artifact.name}")
                except Exception as e:
                    print(f"[OTA-SIGN] ❌ 签名失败: {artifact.name} - {e}")
            
            if signatures:
                # 保存签名信息
                self._save_signatures(version, signatures)
                print(f"[OTA-SIGN] ✅ OTA签名完成: {len(signatures)} 个文件")
                return True
            else:
                print("[OTA-SIGN] ❌ 所有文件签名失败")
                return False
            
        except ImportError:
            print("[OTA-SIGN] ❌ 缺少cryptography库")
            return False
        except Exception as e:
            print(f"[OTA-SIGN] ❌ OTA签名失败: {e}")
            return False
    
    def _save_signatures(self, version: str, signatures: Dict[str, Any]):
        """保存签名信息到JSON文件"""
        try:
            ota_server_dir = self.project_root / "ota" / "server"
            ota_server_dir.mkdir(parents=True, exist_ok=True)
            
            signatures_file = ota_server_dir / f"signatures_{version}.json"
            
            with open(signatures_file, 'w', encoding='utf-8') as f:
                json.dump(signatures, f, indent=2, ensure_ascii=False)
            
            print(f"[OTA-SIGN] ✅ 签名信息已保存: {signatures_file}")
            
        except Exception as e:
            print(f"[OTA-SIGN] ⚠️ 保存签名信息失败: {e}")

def create_signing_manager(project_root: Path = None, config: Dict[str, Any] = None) -> SigningManager:
    """创建签名管理器实例"""
    return SigningManager(project_root, config)

def create_ota_signing_manager(project_root: Path = None) -> OTASigningManager:
    """创建OTA签名管理器实例"""
    return OTASigningManager(project_root)
