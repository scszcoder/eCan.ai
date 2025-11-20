#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
eCan.ai Build System Signing Manager
Integrates code signing and OTA signing into the build process
"""

import os
import json
import subprocess
import platform
import re
from pathlib import Path
from typing import Dict, Any, Optional

class SigningManager:
    """Code signing manager"""
    
    def __init__(self, project_root: Path = None, config: Dict[str, Any] = None):
        self.project_root = project_root or Path.cwd()
        self.config = config or {}
        self.platform = platform.system().lower()
        self.dist_dir = self.project_root / "dist"
    
    def _resolve_password(self, password_config: str, config: Dict[str, Any]) -> str:
        """
        Resolve password configuration, supports environment variables and default password fallback
        
        Args:
            password_config: Password field in config, may be environment variable format ${VAR_NAME}
            config: Signing configuration dictionary
            
        Returns:
            Resolved password string
        """
        if not password_config:
            # If password config is empty, try to use default password
            default_password = config.get("default_password", "")
            if default_password:
                print(f"[SIGN] Using default password from config file")
                return default_password
            return ""
        
        # Check if it's environment variable format ${VAR_NAME}
        env_var_pattern = r'\$\{([^}]+)\}'
        match = re.match(env_var_pattern, password_config)
        
        if match:
            env_var_name = match.group(1)
            env_password = os.getenv(env_var_name)
            
            if env_password:
                print(f"[SIGN] Using password from environment variable {env_var_name}")
                return env_password
            else:
                print(f"[SIGN] Environment variable {env_var_name} not set or empty, trying default password")
                # When environment variable is empty, try to use default password
                default_password = config.get("default_password", "")
                if default_password:
                    print(f"[SIGN] Using default password from config file")
                    return default_password
                else:
                    print(f"[SIGN] Warning: Environment variable {env_var_name} and default password not set, using empty password")
                    return ""
        else:
            # Use password directly from config
            return password_config
        
    def should_sign(self, mode: str = "prod") -> bool:
        """Determine whether signing should be performed"""
        # Development mode usually skips signing to speed up build
        if mode == "dev":
            return False
        
        # Check platform configuration
        platform_config = self.config.get("platforms", {})
        
        if self.platform == "windows":
            return platform_config.get("windows", {}).get("sign", {}).get("enabled", False)
        elif self.platform == "darwin":
            return platform_config.get("macos", {}).get("codesign", {}).get("enabled", False)
        
        return False
    
    def sign_artifacts(self, mode: str = "prod") -> bool:
        """Sign build artifacts"""
        if not self.should_sign(mode):
            print("[SIGN] Signing disabled or current platform not supported")
            return True
        
        print(f"[SIGN] Starting to sign build artifacts (mode: {mode})")
        
        try:
            if self.platform == "windows":
                return self._sign_windows_artifacts()
            elif self.platform == "darwin":
                return self._sign_macos_artifacts()
            else:
                print(f"[SIGN] Unsupported platform: {self.platform}")
                return True
                
        except Exception as e:
            print(f"[SIGN] Error during signing process: {e}")
            # Signing failure should not block build, just warning
            return True
    
    def _sign_windows_artifacts(self) -> bool:
        """Sign Windows build artifacts"""
        print("[SIGN] Executing Windows code signing...")
        
        config = self.config.get("platforms", {}).get("windows", {}).get("sign", {})
        signtool = config.get("tool", "signtool")
        
        if not self._check_tool_available(signtool):
            print(f"[SIGN] Warning: {signtool} not available, skipping signing")
            return True
        
        # Find files to sign
        files_to_sign = list(self.dist_dir.rglob("*.exe")) + list(self.dist_dir.rglob("*.dll"))
        
        if not files_to_sign:
            print("[SIGN] No Windows files found to sign")
            return True
        
        # Sign files
        success_count = sum(1 for f in files_to_sign if self._sign_windows_file(f, config))
        print(f"[SIGN] Windows signing completed: {success_count}/{len(files_to_sign)} files")
        return success_count > 0
    
    def _sign_windows_file(self, file_path: Path, config: Dict[str, Any]) -> bool:
        """Sign single Windows file"""
        try:
            # Build signing command
            cmd = [
                config.get("tool", "signtool"), "sign",
                "/f", config.get("certificate", ""),
                "/fd", "SHA256",
                "/tr", "http://timestamp.digicert.com",
                "/td", "SHA256",
                str(file_path)
            ]
            
            # Parse and add password (if any)
            password_config = config.get("password", "")
            password = self._resolve_password(password_config, config)
            if password:
                cmd.insert(-1, "/p")
                cmd.insert(-1, password)
            
            # Filter empty arguments
            cmd = [arg for arg in cmd if arg]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            if result.returncode == 0:
                print(f"[SIGN] [OK] Signed: {file_path.name}")
                return True
            else:
                print(f"[SIGN] [ERROR] Signing failed: {file_path.name} - {result.stderr.strip()}")
                return False
                
        except Exception as e:
            print(f"[SIGN] [ERROR] Signing exception: {file_path.name} - {e}")
            return False
    
    def _sign_macos_artifacts(self) -> bool:
        """Sign macOS build artifacts"""
        print("[SIGN] Executing macOS code signing...")
        
        config = self.config.get("platforms", {}).get("macos", {}).get("codesign", {})
        
        if not self._check_tool_available("codesign"):
            print("[SIGN] Warning: codesign not available, skipping signing")
            return True
        
        # Find files to sign
        files_to_sign = list(self.dist_dir.rglob("*.app")) + list(self.dist_dir.rglob("*.dylib"))
        
        if not files_to_sign:
            print("[SIGN] No macOS files found to sign")
            return True
        
        # Sign files
        success_count = sum(1 for f in files_to_sign if self._sign_macos_file(f, config))
        print(f"[SIGN] macOS signing completed: {success_count}/{len(files_to_sign)} files")
        return success_count > 0
    
    def _sign_macos_file(self, file_path: Path, config: Dict[str, Any]) -> bool:
        """Sign single macOS file"""
        try:
            identity = config.get("identity", "")
            if not identity:
                print(f"[SIGN] Warning: Signing identity not configured")
                return False
            
            cmd = ["codesign", "--sign", identity, "--force", "--timestamp", str(file_path)]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            if result.returncode == 0:
                print(f"[SIGN] [OK] Signed: {file_path.name}")
                return True
            else:
                print(f"[SIGN] [ERROR] Signing failed: {file_path.name} - {result.stderr.strip()}")
                return False
                
        except Exception as e:
            print(f"[SIGN] [ERROR] Signing exception: {file_path.name} - {e}")
            return False
    
    def _check_tool_available(self, tool: str) -> bool:
        """Check if signing tool is available"""
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
            return True  # Tool exists but may be waiting for parameters
        except Exception:
            return False
    
    def verify_signatures(self) -> bool:
        """Verify signatures"""
        print("[VERIFY] Verifying build artifact signatures...")
        
        try:
            if self.platform == "windows":
                return self._verify_windows_signatures()
            elif self.platform == "darwin":
                return self._verify_macos_signatures()
            else:
                print(f"[VERIFY] Current platform {self.platform} does not require verification")
                return True
        except Exception as e:
            print(f"[VERIFY] Error during verification process: {e}")
            return True
    
    def _verify_windows_signatures(self) -> bool:
        """Verify Windows signatures"""
        if not self._check_tool_available("signtool"):
            print("[VERIFY] signtool not available, skipping verification")
            return True
        
        signed_files = list(self.dist_dir.rglob("*.exe")) + list(self.dist_dir.rglob("*.dll"))
        
        if not signed_files:
            print("[VERIFY] No files found to verify")
            return True
        
        verified_count = 0
        for file_path in signed_files:
            try:
                result = subprocess.run(
                    ["signtool", "verify", "/pa", str(file_path)],
                    capture_output=True, text=True, timeout=30
                )
                
                if result.returncode == 0:
                    # print(f"[VERIFY] [OK] Signature valid: {file_path.name}")
                    verified_count += 1
                else:
                    print(f"[VERIFY] [ERROR] Signature invalid: {file_path.name}")
            except Exception as e:
                print(f"[VERIFY] [ERROR] Verification failed: {file_path.name} - {e}")
        
        print(f"[VERIFY] Windows signature verification: {verified_count}/{len(signed_files)} files")
        return verified_count > 0
    
    def _verify_macos_signatures(self) -> bool:
        """Verify macOS signatures"""
        if not self._check_tool_available("codesign"):
            print("[VERIFY] codesign not available, skipping verification")
            return True
        
        signed_files = list(self.dist_dir.rglob("*.app")) + list(self.dist_dir.rglob("*.dylib"))
        
        if not signed_files:
            print("[VERIFY] No files found to verify")
            return True
        
        verified_count = 0
        for file_path in signed_files:
            try:
                result = subprocess.run(
                    ["codesign", "--verify", str(file_path)],
                    capture_output=True, text=True, timeout=30
                )
                
                if result.returncode == 0:
                    # print(f"[VERIFY] [OK] Signature valid: {file_path.name}")
                    verified_count += 1
                else:
                    print(f"[VERIFY] [ERROR] Signature invalid: {file_path.name}")
            except Exception as e:
                print(f"[VERIFY] [ERROR] Verification failed: {file_path.name} - {e}")
        
        print(f"[VERIFY] macOS signature verification: {verified_count}/{len(signed_files)} files")
        return verified_count > 0

class OTASigningManager:
    """OTA signing manager - using Ed25519 signing algorithm"""
    
    def __init__(self, project_root: Path = None):
        self.project_root = project_root or Path.cwd()
        self.private_key_path = self.project_root / "build_system" / "certificates" / "ed25519_private_key.pem"
        self.dist_dir = self.project_root / "dist"
    
    def sign_for_ota(self, version: str) -> bool:
        """Sign build artifacts for OTA distribution"""
        print(f"[OTA-SIGN] Sign build artifacts for OTA distribution (version: {version})")
        
        try:
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.asymmetric import ed25519
            import base64
            
            # Load private key
            if not self.private_key_path.exists():
                print(f"[OTA-SIGN] [ERROR] Ed25519 private key file does not exist: {self.private_key_path}")
                return False
            
            with open(self.private_key_path, 'rb') as f:
                private_key = serialization.load_pem_private_key(f.read(), password=None)
            
            if not isinstance(private_key, ed25519.Ed25519PrivateKey):
                print("[OTA-SIGN] [ERROR] Private key format is incorrect")
                return False
            
            # Find distribution files to sign
            artifacts = list(self.dist_dir.glob("*.exe")) + list(self.dist_dir.glob("*.dmg")) + list(self.dist_dir.glob("*.pkg"))
            
            if not artifacts:
                print("[OTA-SIGN] [ERROR] No distribution files found to sign")
                return False
            
            signatures = {}
            
            # Sign each file
            for artifact in artifacts:
                print(f"[OTA-SIGN] Signing: {artifact.name}")
                
                try:
                    # Read file content
                    with open(artifact, 'rb') as f:
                        file_data = f.read()
                    
                    # Generate Ed25519 signature
                    signature = private_key.sign(file_data)
                    signature_b64 = base64.b64encode(signature).decode('ascii')
                    
                    signatures[artifact.name] = {
                        "signature": signature_b64,
                        "algorithm": "Ed25519",
                        "file_size": len(file_data)
                    }
                    
                    # Also save signature to .sig file for upload
                    # Sparkle-compatible format: base64 Ed25519 signature in .sig file
                    # Our self-contained OTA system reads this format
                    sig_file = artifact.with_suffix(artifact.suffix + '.sig')
                    with open(sig_file, 'w', encoding='utf-8') as f:
                        f.write(signature_b64)
                    print(f"[OTA-SIGN] [OK] Created signature file: {sig_file.name}")
                    
                    print(f"[OTA-SIGN] [OK] Signed: {artifact.name}")
                except Exception as e:
                    print(f"[OTA-SIGN] [ERROR] Signing failed: {artifact.name} - {e}")
            
            if signatures:
                # Save signature information
                self._save_signatures(version, signatures)
                print(f"[OTA-SIGN] [OK] OTA signing completed: {len(signatures)} files")
                return True
            else:
                print("[OTA-SIGN] [ERROR] All files signing failed")
                return False
            
        except ImportError:
            print("[OTA-SIGN] [ERROR] Missing cryptography library")
            return False
        except Exception as e:
            print(f"[OTA-SIGN] [ERROR] OTA signing failed: {e}")
            return False
    
    def _save_signatures(self, version: str, signatures: Dict[str, Any]):
        """Save signature information to JSON file"""
        try:
            ota_server_dir = self.project_root / "ota" / "server"
            ota_server_dir.mkdir(parents=True, exist_ok=True)
            
            signatures_file = ota_server_dir / f"signatures_{version}.json"
            
            with open(signatures_file, 'w', encoding='utf-8') as f:
                json.dump(signatures, f, indent=2, ensure_ascii=False)
            
            print(f"[OTA-SIGN] [OK] Signature information saved: {signatures_file}")
            
        except Exception as e:
            print(f"[OTA-SIGN] [WARNING] Failed to save signature information: {e}")

def create_signing_manager(project_root: Path = None, config: Dict[str, Any] = None) -> SigningManager:
    """Create signing manager instance"""
    return SigningManager(project_root, config)

def create_ota_signing_manager(project_root: Path = None) -> OTASigningManager:
    """Create OTA signing manager instance"""
    return OTASigningManager(project_root)
