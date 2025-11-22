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
        
        # Check if certificate exists before attempting to sign
        cert_path = config.get("certificate", "")
        if cert_path and not Path(cert_path).exists():
            print(f"[SIGN] Certificate file not found: {cert_path}")
            print(f"[SIGN] Skipping Windows code signing (certificate not available)")
            return True
        
        if not cert_path:
            print(f"[SIGN] No certificate configured, skipping Windows code signing")
            return True
        
        if not self._check_tool_available(signtool):
            print(f"[SIGN] Warning: {signtool} not available, skipping signing")
            return True
        
        # Find files to sign
        all_files = list(self.dist_dir.rglob("*.exe")) + list(self.dist_dir.rglob("*.dll"))
        
        # Filter out system DLLs that should not be signed
        files_to_sign = [f for f in all_files if not self._is_system_dll(f)]
        
        skipped_count = len(all_files) - len(files_to_sign)
        if skipped_count > 0:
            print(f"[SIGN] Skipped {skipped_count} system DLL(s) (already signed by Microsoft)")
        
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
            # Check if certificate file exists
            cert_path = config.get("certificate", "")
            if cert_path and not Path(cert_path).exists():
                print(f"[SIGN] Certificate file not found: {cert_path}, skipping signing")
                return True  # Not a failure, just skip signing
            
            if not cert_path:
                print(f"[SIGN] No certificate configured, skipping signing")
                return True
            
            # Build signing command
            cmd = [
                config.get("tool", "signtool"), "sign",
                "/f", cert_path,
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
        
        # Check if signing identity is configured
        identity = config.get("identity", "")
        if not identity:
            print(f"[SIGN] Signing identity not configured, skipping macOS code signing")
            return True
        
        if not self._check_tool_available("codesign"):
            print("[SIGN] Warning: codesign not available, skipping signing")
            return True
        
        # Find files to sign
        all_files = list(self.dist_dir.rglob("*.app")) + list(self.dist_dir.rglob("*.dylib")) + list(self.dist_dir.rglob("*.framework"))
        
        # Filter out system frameworks and libraries that should not be signed
        files_to_sign = [f for f in all_files if not self._is_system_framework(f)]
        
        skipped_count = len(all_files) - len(files_to_sign)
        if skipped_count > 0:
            print(f"[SIGN] Skipped {skipped_count} system framework(s)/library(ies) (already signed by Apple)")
        
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
                print(f"[SIGN] Signing identity not configured, skipping signing")
                return True  # Not a failure, just skip signing
            
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
    
    def _is_system_dll(self, file_path: Path) -> bool:
        """
        Check if a DLL/EXE is a Windows system file that should not be signed
        
        System files are already signed by Microsoft/vendors and should not be re-signed.
        These include:
        - api-ms-win-*.dll (Windows API sets)
        - ucrtbase.dll (Universal C Runtime)
        - vcruntime*.dll (Visual C++ Runtime)
        - msvcp*.dll (Microsoft C++ Standard Library)
        - Third-party bundled apps (Playwright browsers, etc.)
        """
        path_str = str(file_path).lower()
        filename = file_path.name.lower()
        
        # Check if it's in a third-party directory
        third_party_paths = [
            'third_party\\',     # Third-party bundled components (Windows path)
            'third_party/',      # Third-party bundled components (Unix-style path)
            'ms-playwright\\',   # Playwright browsers (Windows path)
            'ms-playwright/',    # Playwright browsers (Unix-style path)
        ]
        
        # Check third-party paths first
        if any(tp_path in path_str for tp_path in third_party_paths):
            return True
        
        # List of system DLL patterns
        system_dll_patterns = [
            'api-ms-win-',      # Windows API sets (e.g., api-ms-win-core-file-l1-1-0.dll)
            'api-ms-win-crt-',  # Windows CRT API sets
            'ucrtbase',         # Universal C Runtime base
            'vcruntime',        # Visual C++ Runtime
            'msvcp',            # Microsoft C++ Standard Library
            'concrt',           # Concurrency Runtime
            'vccorlib',         # Visual C++ Core Library
        ]
        
        # Third-party bundled applications (already signed by vendors)
        third_party_apps = [
            'chrome.exe',       # Playwright Chromium
            'chrome.dll',       # Chromium libraries
            'firefox.exe',      # Playwright Firefox
            'webkit.exe',       # Playwright WebKit
        ]
        
        # Check system DLL patterns
        if any(filename.startswith(pattern) for pattern in system_dll_patterns):
            return True
        
        # Check third-party apps
        if any(app in filename for app in third_party_apps):
            return True
        
        return False
    
    def _is_system_framework(self, file_path: Path) -> bool:
        """
        Check if a file is a macOS system framework/library that should not be signed
        
        System frameworks are already signed by Apple/vendors and should not be re-signed.
        These include:
        - Qt frameworks (from PySide6/PyQt)
        - Python system libraries
        - macOS system frameworks
        - Third-party bundled apps (Playwright Chromium, etc.)
        """
        path_str = str(file_path).lower()
        filename = file_path.name.lower()
        
        # Check if it's in a system or third-party framework directory
        system_paths = [
            '/system/library/frameworks/',
            '/library/frameworks/',
            'python3.',  # Python system libraries
            'site-packages',  # Third-party packages
            '.framework/versions/',  # System frameworks
            'third_party/',  # Third-party bundled components
            'ms-playwright/',  # Playwright browsers
        ]
        
        # Qt frameworks from PySide6/PyQt (already signed)
        qt_frameworks = [
            'qtcore',
            'qtgui',
            'qtwidgets',
            'qtnetwork',
            'qtwebengine',
            'qtwebenginecore',
            'qtwebenginewidgets',
            'qtprintsupport',
            'qtdbus',
            'qtopengl',
        ]
        
        # Third-party bundled applications (already signed by vendors)
        third_party_apps = [
            'chromium',  # Playwright Chromium
            'firefox',   # Playwright Firefox
            'webkit',    # Playwright WebKit
        ]
        
        # Check system paths
        if any(sys_path in path_str for sys_path in system_paths):
            return True
        
        # Check Qt frameworks
        if any(qt_fw in filename for qt_fw in qt_frameworks):
            return True
        
        # Check third-party apps
        if any(app in filename for app in third_party_apps):
            return True
        
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
        
        # Find all files and filter out system DLLs
        all_files = list(self.dist_dir.rglob("*.exe")) + list(self.dist_dir.rglob("*.dll"))
        signed_files = [f for f in all_files if not self._is_system_dll(f)]
        
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
        
        # Find all files and filter out system frameworks
        all_files = list(self.dist_dir.rglob("*.app")) + list(self.dist_dir.rglob("*.dylib")) + list(self.dist_dir.rglob("*.framework"))
        signed_files = [f for f in all_files if not self._is_system_framework(f)]
        
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
                    
                    # Save signature to .sig file for upload
                    # Save as binary (64 bytes) for Sparkle compatibility
                    # The generate_appcast.py script will read this binary and base64 encode it
                    sig_file = artifact.with_suffix(artifact.suffix + '.sig')
                    with open(sig_file, 'wb') as f:
                        f.write(signature)  # Write raw 64-byte signature
                    
                    # Verify signature file size
                    if sig_file.stat().st_size == 64:
                        print(f"[OTA-SIGN] [OK] Created signature file: {sig_file.name} (64 bytes)")
                    else:
                        print(f"[OTA-SIGN] [ERROR] Invalid signature size: {sig_file.stat().st_size} bytes (expected 64)")
                        continue
                    
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

def sign_single_file_ed25519(file_path: str, private_key_path: str, output_sig_path: str = None) -> bool:
    """
    Sign a single file with Ed25519 (command-line interface)
    
    Args:
        file_path: Path to file to sign
        private_key_path: Path to Ed25519 private key (PEM format)
        output_sig_path: Path to output signature file (default: file_path + '.sig')
    
    Returns:
        True if successful, False otherwise
    """
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ed25519
    except ImportError:
        print("❌ Error: cryptography library not installed")
        print("Install with: pip install cryptography")
        return False
    
    # Convert to Path objects
    file_path = Path(file_path)
    private_key_path = Path(private_key_path)
    output_sig_path = Path(output_sig_path) if output_sig_path else file_path.with_suffix(file_path.suffix + '.sig')
    
    # Validate inputs
    if not file_path.exists():
        print(f"❌ Error: File not found: {file_path}")
        return False
    
    if not private_key_path.exists():
        print(f"❌ Error: Private key not found: {private_key_path}")
        return False
    
    try:
        # Read private key
        print(f"📖 Reading private key: {private_key_path}")
        with open(private_key_path, 'rb') as f:
            private_key = serialization.load_pem_private_key(f.read(), password=None)
        
        # Verify it's an Ed25519 key
        if not isinstance(private_key, ed25519.Ed25519PrivateKey):
            print(f"❌ Error: Key is not Ed25519 (got {type(private_key).__name__})")
            return False
        
        print(f"✅ Private key loaded successfully")
        
        # Read file to sign
        print(f"📖 Reading file to sign: {file_path}")
        with open(file_path, 'rb') as f:
            file_data = f.read()
        
        file_size_mb = len(file_data) / (1024 * 1024)
        print(f"✅ File loaded: {file_size_mb:.2f} MB")
        
        # Generate signature
        print(f"🔐 Generating Ed25519 signature...")
        signature = private_key.sign(file_data)
        
        # Verify signature size (Ed25519 signatures are always 64 bytes)
        if len(signature) != 64:
            print(f"❌ Error: Invalid signature size: {len(signature)} bytes (expected 64)")
            return False
        
        print(f"✅ Signature generated: {len(signature)} bytes")
        
        # Write signature to file
        print(f"💾 Writing signature to: {output_sig_path}")
        with open(output_sig_path, 'wb') as sig_file:
            sig_file.write(signature)
        
        print(f"✅ Signature file created successfully")
        
        # Verify the signature was written correctly
        if output_sig_path.exists():
            sig_size = output_sig_path.stat().st_size
            if sig_size == 64:
                print(f"✅ Verification: Signature file is 64 bytes")
                return True
            else:
                print(f"❌ Error: Signature file size mismatch: {sig_size} bytes")
                return False
        else:
            print(f"❌ Error: Signature file was not created")
            return False
            
    except Exception as e:
        print(f"❌ Error during signing: {e}")
        import traceback
        traceback.print_exc()
        return False

# Command-line interface
if __name__ == '__main__':
    import sys
    
    if len(sys.argv) >= 3:
        file_path = sys.argv[1]
        private_key_path = sys.argv[2]
        output_sig_path = sys.argv[3] if len(sys.argv) > 3 else None
        
        print("=" * 60)
        print("Ed25519 File Signing")
        print("=" * 60)
        print(f"File to sign: {file_path}")
        print(f"Private key:  {private_key_path}")
        print(f"Output sig:   {output_sig_path or file_path + '.sig'}")
        print("=" * 60)
        print()
        
        success = sign_single_file_ed25519(file_path, private_key_path, output_sig_path)
        
        print()
        print("=" * 60)
        if success:
            print("✅ Signing completed successfully")
            print("=" * 60)
            sys.exit(0)
        else:
            print("❌ Signing failed")
            print("=" * 60)
            sys.exit(1)
    else:
        print("Usage: python signing_manager.py <file_to_sign> <private_key_path> [output_sig_path]")
        print()
        print("Example:")
        print("  python signing_manager.py dist/eCan-1.0.0.pkg build_system/certificates/ed25519_private_key.pem")
        sys.exit(1)
