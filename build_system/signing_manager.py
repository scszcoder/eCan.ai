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

def _is_system_dll(file_path: Path) -> bool:
    """Module-level helper: return True for system/third-party DLLs that must not be re-signed."""
    path_str = str(file_path).lower()
    filename = file_path.name.lower()
    third_party_paths = ['third_party\\', 'third_party/', 'ms-playwright\\', 'ms-playwright/']
    if any(tp in path_str for tp in third_party_paths):
        return True
    system_patterns = ['api-ms-win-', 'api-ms-win-crt-', 'ucrtbase', 'vcruntime', 'msvcp', 'concrt', 'vccorlib']
    third_party_apps = ['chrome.exe', 'chrome.dll', 'firefox.exe', 'webkit.exe']
    if any(filename.startswith(p) for p in system_patterns):
        return True
    if any(app in filename for app in third_party_apps):
        return True
    return False


class AzureTrustedSigningManager:
    """
    Azure Trusted Signing (cloud HSM) manager for Windows code signing.
    
    Private key never leaves Azure HSM. Uses service principal authentication.
    
    Required environment variables:
        AZURE_TENANT_ID        - Azure AD Tenant ID
        AZURE_CLIENT_ID        - Service Principal Application ID
        AZURE_CLIENT_SECRET    - Service Principal Secret
        AZURE_SIGNING_ENDPOINT - e.g. https://eus.codesigning.azure.net
        AZURE_SIGNING_ACCOUNT  - Trusted Signing account name
        AZURE_SIGNING_PROFILE  - Certificate profile name
    """

    TIMESTAMP_URL = "http://timestamp.acs.microsoft.com"
    NUGET_PACKAGE = "Microsoft.Trusted.Signing.Client"

    def __init__(self, project_root: Path = None):
        self.project_root = project_root or Path.cwd()
        self.dist_dir = self.project_root / "dist"
        self._package_dir: Optional[Path] = None
        self._dlib_path: Optional[Path] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_configured(self) -> bool:
        """Return True when all required env vars are present."""
        required = [
            "AZURE_TENANT_ID",
            "AZURE_CLIENT_ID",
            "AZURE_CLIENT_SECRET",
            "AZURE_SIGNING_ENDPOINT",
            "AZURE_SIGNING_ACCOUNT",
            "AZURE_SIGNING_PROFILE",
        ]
        missing = [k for k in required if not os.getenv(k)]
        if missing:
            print(f"[AZURE-SIGN] Missing env vars: {', '.join(missing)}")
            return False
        return True

    def sign_windows_artifacts(self, files_folder: Optional[Path] = None) -> bool:
        """Sign all EXE/DLL files in *files_folder* (default: dist/)."""
        if not self.is_configured():
            print("[AZURE-SIGN] Azure Trusted Signing not configured – skipping")
            return False

        folder = files_folder or self.dist_dir
        print(f"[AZURE-SIGN] Signing artifacts in: {folder}")

        if not self._ensure_dlib():
            return False

        metadata_path = self._write_metadata()
        if not metadata_path:
            return False

        signtool = self._find_signtool()
        if not signtool:
            print("[AZURE-SIGN] signtool.exe not found")
            return False

        files = self._collect_files(folder)
        if not files:
            print("[AZURE-SIGN] No files to sign")
            return True

        ok = sum(1 for f in files if self._sign_one(f, signtool, metadata_path))
        print(f"[AZURE-SIGN] Done: {ok}/{len(files)} files signed")
        return ok == len(files)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_dlib(self) -> bool:
        """Install NuGet package and locate the signing dlib."""
        if self._dlib_path and self._dlib_path.exists():
            return True

        import tempfile, shutil
        tmp = Path(tempfile.gettempdir()) / "azure-trusted-signing"
        tmp.mkdir(parents=True, exist_ok=True)

        nuget = self._get_nuget(tmp)
        if not nuget:
            return False

        pkg_dir = tmp / "packages"
        pkg_dir.mkdir(exist_ok=True)

        print(f"[AZURE-SIGN] Installing {self.NUGET_PACKAGE}...")
        result = subprocess.run(
            [str(nuget), "install", self.NUGET_PACKAGE,
             "-OutputDirectory", str(pkg_dir),
             "-NonInteractive", "-Verbosity", "quiet"],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode != 0:
            print(f"[AZURE-SIGN] NuGet install failed: {result.stderr.strip()}")
            return False

        # Locate dlib (prefer win-x64)
        candidates = list(pkg_dir.rglob("Azure.CodeSigning.Dlib.dll"))
        preferred = [c for c in candidates if "win-x64" in str(c)]
        dlib = (preferred or candidates)
        if not dlib:
            print("[AZURE-SIGN] Azure.CodeSigning.Dlib.dll not found in package")
            return False

        self._dlib_path = dlib[0]
        print(f"[AZURE-SIGN] dlib: {self._dlib_path}")
        return True

    def _get_nuget(self, tmp: Path) -> Optional[Path]:
        """Download nuget.exe if not present."""
        nuget = tmp / "nuget.exe"
        if nuget.exists():
            return nuget
        try:
            import urllib.request
            print("[AZURE-SIGN] Downloading nuget.exe...")
            urllib.request.urlretrieve(
                "https://dist.nuget.org/win-x86-commandline/latest/nuget.exe",
                str(nuget)
            )
            return nuget
        except Exception as e:
            print(f"[AZURE-SIGN] Failed to download nuget.exe: {e}")
            return None

    def _write_metadata(self) -> Optional[Path]:
        """Write the JSON metadata file consumed by the dlib."""
        import tempfile
        meta = {
            "Endpoint": os.getenv("AZURE_SIGNING_ENDPOINT", ""),
            "CodeSigningAccountName": os.getenv("AZURE_SIGNING_ACCOUNT", ""),
            "CertificateProfileName": os.getenv("AZURE_SIGNING_PROFILE", ""),
            "ExcludeCredentials": [],
        }
        path = Path(tempfile.gettempdir()) / "azure-signing-metadata.json"
        try:
            path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
            return path
        except Exception as e:
            print(f"[AZURE-SIGN] Failed to write metadata: {e}")
            return None

    def _find_signtool(self) -> Optional[str]:
        """Locate signtool.exe on the system."""
        try:
            result = subprocess.run(["signtool"], capture_output=True, timeout=5)
            return "signtool"
        except FileNotFoundError:
            pass

        sdk_roots = [
            r"C:\Program Files (x86)\Windows Kits\10\bin",
            r"C:\Program Files\Windows Kits\10\bin",
        ]
        for root in sdk_roots:
            root_path = Path(root)
            if not root_path.exists():
                continue
            for candidate in sorted(root_path.iterdir(), reverse=True):
                st = candidate / "x64" / "signtool.exe"
                if st.exists():
                    return str(st)
        return None

    def _collect_files(self, folder: Path):
        """Collect EXE/DLL files, excluding system and third-party binaries."""
        all_files = list(folder.rglob("*.exe")) + list(folder.rglob("*.dll"))
        return [f for f in all_files if not _is_system_dll(f)]

    def _sign_one(self, file_path: Path, signtool: str, metadata_path: Path) -> bool:
        """Sign a single file via Azure Trusted Signing dlib."""
        env = os.environ.copy()
        env.update({
            "AZURE_TENANT_ID": os.getenv("AZURE_TENANT_ID", ""),
            "AZURE_CLIENT_ID": os.getenv("AZURE_CLIENT_ID", ""),
            "AZURE_CLIENT_SECRET": os.getenv("AZURE_CLIENT_SECRET", ""),
        })
        cmd = [
            signtool, "sign",
            "/fd", "SHA256",
            "/p7ce", "DetachedSignedData",
            "/dlib", str(self._dlib_path),
            "/dmdf", str(metadata_path),
            "/tr", self.TIMESTAMP_URL,
            "/td", "SHA256",
            str(file_path),
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, env=env)
            if result.returncode == 0:
                print(f"[AZURE-SIGN] [OK] {file_path.name}")
                return True
            print(f"[AZURE-SIGN] [ERROR] {file_path.name}: {result.stderr.strip()}")
            return False
        except Exception as e:
            print(f"[AZURE-SIGN] [ERROR] {file_path.name}: {e}")
            return False


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

    def _can_verify_signatures(self) -> bool:
        """Return True if signature verification should run for this build.

        In CI builds we often don't have access to signing credentials. In that case we
        still want the build to proceed (unsigned), so verification should be skipped.
        """
        try:
            platform_config = self.config.get("platforms", {})

            if self.platform == "windows":
                sign_cfg = platform_config.get("windows", {}).get("sign", {})
                if not sign_cfg.get("enabled", False):
                    return False
                cert_path = sign_cfg.get("certificate", "")
                if not cert_path or not Path(cert_path).exists():
                    return False
                if not self._check_tool_available("signtool"):
                    return False
                return True

            if self.platform == "darwin":
                sign_cfg = platform_config.get("macos", {}).get("codesign", {})
                if not sign_cfg.get("enabled", False):
                    return False
                identity = sign_cfg.get("identity", "")
                if not identity:
                    return False
                if not self._check_tool_available("codesign"):
                    return False
                return True

            return False
        except Exception:
            return False
    
    def verify_signatures(self) -> bool:
        """Verify signatures"""
        print("[VERIFY] Verifying build artifact signatures...")

        if not self._can_verify_signatures():
            print("[VERIFY] Skipping signature verification (signing not configured or credentials/tools unavailable)")
            return True
        
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
        # The key file path can be overridden via OTA_PRIVATE_KEY_PATH
        # (used by GitHub Actions self-hosted runner workflows that
        # write the key to a per-job ephemeral location under
        # RUNNER_TEMP to avoid ACL hardening on persistent workspace
        # paths). Falls back to the canonical project-root-relative
        # location so existing local-dev and Linux CI usage still
        # works without any environment setup.
        override = os.environ.get('OTA_PRIVATE_KEY_PATH')
        if override:
            self.private_key_path = Path(override)
        else:
            self.private_key_path = (
                self.project_root
                / 'build_system' / 'certificates' / 'ed25519_private_key.pem'
            )
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
            # Look for installer files, not internal executables
            # Expected formats:
            #   Windows: eCan-{version}-windows-{arch}-Setup.exe, *.msi
            #   macOS:   eCan-{version}-macos-{arch}.pkg, *.dmg
            #   Linux:   *.deb, *.rpm
            artifacts = (
                list(self.dist_dir.glob("*-Setup.exe")) +  # Windows Inno Setup installers
                list(self.dist_dir.glob("*.msi")) +         # Windows MSI installers
                list(self.dist_dir.glob("*-macos-*.pkg")) + # macOS PKG installers
                list(self.dist_dir.glob("*.dmg")) +         # macOS disk images
                list(self.dist_dir.glob("*.deb")) +         # Linux DEB packages
                list(self.dist_dir.glob("*.rpm"))           # Linux RPM packages
            )
            
            if not artifacts:
                print("[OTA-SIGN] [ERROR] No distribution files found to sign")
                print(f"[OTA-SIGN] [DEBUG] Searched in: {self.dist_dir}")
                print(f"[OTA-SIGN] [DEBUG] Looking for: *-Setup.exe, *.msi, *-macos-*.pkg, *.dmg, *.deb, *.rpm")
                # List what files are actually in dist/
                dist_files = list(self.dist_dir.glob("*"))
                if dist_files:
                    print(f"[OTA-SIGN] [DEBUG] Files found in dist/:")
                    for f in dist_files[:10]:  # Show first 10 files
                        print(f"[OTA-SIGN] [DEBUG]   - {f.name}")
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
                # NOTE: Historically this wrote ``ota/server/signatures_{version}.json``
                # alongside the per-artifact ``.sig`` files. The JSON sidecar is not
                # read by ``build_system/scripts/generate_appcast.py``, not uploaded
                # by ``build_system/scripts/upload_to_{s3,cos}.py``, and not consulted
                # by the client (see ``ota/core/appcast.py``). The ``.sig`` files
                # are the single source of truth, so the JSON write is now a no-op.
                # Kept as a log-only shim so external callers (if any) still get
                # back a callable that doesn't write misleading files.
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
        """Deprecated log-only shim. Previously wrote
        ``ota/server/signatures_{version}.json``; that sidecar is no longer
        produced or consumed. Per-artifact ``.sig`` files are the single
        source of truth for OTA signatures.
        """
        # Intentionally do NOT write a JSON sidecar. Keeping a callable here
        # so any external import still resolves and so the function name
        # remains discoverable in stack traces during the deprecation window.
        try:
            print(
                f"[OTA-SIGN] [DEPRECATED] _save_signatures is a no-op; "
                f"per-artifact .sig files for {len(signatures)} artifact(s) "
                f"are the single source of truth for version {version}."
            )
        except Exception as e:
            print(f"[OTA-SIGN] [WARNING] Failed to log deprecation notice: {e}")

def create_signing_manager(project_root: Path = None, config: Dict[str, Any] = None) -> SigningManager:
    """Create signing manager instance"""
    return SigningManager(project_root, config)

def create_ota_signing_manager(project_root: Path = None) -> OTASigningManager:
    """Create OTA signing manager instance"""
    return OTASigningManager(project_root)

def create_azure_signing_manager(project_root: Path = None) -> AzureTrustedSigningManager:
    """Create Azure Trusted Signing manager instance (cloud HSM, preferred for Windows)"""
    return AzureTrustedSigningManager(project_root)

def sign_windows_with_best_available(project_root: Path = None, config: Dict[str, Any] = None) -> bool:
    """
    Sign Windows artifacts using the best available method:
      1. Azure Trusted Signing (cloud HSM) — if env vars configured
      2. PFX certificate file              — if WIN_CERT_PFX / WIN_CERT_PASSWORD set
      3. Skip (return True)                — no credentials available

    Returns True if signing succeeded or was intentionally skipped.
    """
    azure_mgr = AzureTrustedSigningManager(project_root)
    if azure_mgr.is_configured():
        print("[SIGN] Using Azure Trusted Signing (cloud HSM)")
        return azure_mgr.sign_windows_artifacts()

    pfx = os.getenv("WIN_CERT_PFX", "")
    if pfx and pfx != "NOT_SET":
        print("[SIGN] Azure not configured – falling back to PFX certificate")
        mgr = SigningManager(project_root, config or {})
        return mgr._sign_windows_artifacts()

    print("[SIGN] No signing credentials configured – skipping Windows signing")
    return True

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
        print("[ERROR] cryptography library not installed")
        print("Install with: pip install cryptography")
        return False
    
    # Convert to Path objects
    file_path = Path(file_path)
    private_key_path = Path(private_key_path)
    output_sig_path = Path(output_sig_path) if output_sig_path else file_path.with_suffix(file_path.suffix + '.sig')
    
    # Validate inputs
    if not file_path.exists():
        print(f"[ERROR] File not found: {file_path}")
        return False
    
    if not private_key_path.exists():
        print(f"[ERROR] Private key not found: {private_key_path}")
        return False
    
    try:
        # Read private key
        print(f"[INFO] Reading private key: {private_key_path}")
        with open(private_key_path, 'rb') as f:
            private_key = serialization.load_pem_private_key(f.read(), password=None)
        
        # Verify it's an Ed25519 key
        if not isinstance(private_key, ed25519.Ed25519PrivateKey):
            print(f"[ERROR] Key is not Ed25519 (got {type(private_key).__name__})")
            return False
        
        print(f"[OK] Private key loaded successfully")
        
        # Read file to sign
        print(f"[INFO] Reading file to sign: {file_path}")
        with open(file_path, 'rb') as f:
            file_data = f.read()
        
        file_size_mb = len(file_data) / (1024 * 1024)
        print(f"[OK] File loaded: {file_size_mb:.2f} MB")
        
        # Generate signature
        print(f"[INFO] Generating Ed25519 signature...")
        signature = private_key.sign(file_data)
        
        # Verify signature size (Ed25519 signatures are always 64 bytes)
        if len(signature) != 64:
            print(f"[ERROR] Invalid signature size: {len(signature)} bytes (expected 64)")
            return False
        
        print(f"[OK] Signature generated: {len(signature)} bytes")
        
        # Write signature to file
        print(f"[INFO] Writing signature to: {output_sig_path}")
        with open(output_sig_path, 'wb') as sig_file:
            sig_file.write(signature)
        
        print(f"[OK] Signature file created successfully")
        
        # Verify the signature was written correctly
        if output_sig_path.exists():
            sig_size = output_sig_path.stat().st_size
            if sig_size == 64:
                print(f"[OK] Verification: Signature file is 64 bytes")
                return True
            else:
                print(f"[ERROR] Signature file size mismatch: {sig_size} bytes")
                return False
        else:
            print(f"[ERROR] Signature file was not created")
            return False
            
    except Exception as e:
        print(f"[ERROR] Error during signing: {e}")
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
            print("[OK] Signing completed successfully")
            print("=" * 60)
            sys.exit(0)
        else:
            print("[FAILED] Signing failed")
            print("=" * 60)
            sys.exit(1)
    else:
        print("Usage: python signing_manager.py <file_to_sign> <private_key_path> [output_sig_path]")
        print()
        print("Example:")
        print("  python signing_manager.py dist/eCan-1.0.0.pkg build_system/certificates/ed25519_private_key.pem")
        sys.exit(1)
