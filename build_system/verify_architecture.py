#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Architecture verification script for macOS builds
Verifies that the built application has the correct architecture
"""

import os
import sys
import subprocess
import platform
from pathlib import Path


def run_command(cmd, capture_output=True, text=True):
    """Run a command and return the result"""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=capture_output, text=text)
        return result.returncode == 0, result.stdout.strip(), result.stderr.strip()
    except Exception as e:
        return False, "", str(e)


def verify_binary_architecture(binary_path, expected_arch):
    """Verify the architecture of a binary file"""
    if not os.path.exists(binary_path):
        return False, f"Binary not found: {binary_path}"
    
    # Use file command to check architecture
    success, stdout, stderr = run_command(f"file '{binary_path}'")
    if not success:
        return False, f"Failed to check file: {stderr}"
    
    print(f"[ARCH] {binary_path}: {stdout}")
    
    # Use lipo command for detailed architecture info (macOS specific)
    if platform.system() == "Darwin":
        success, lipo_out, lipo_err = run_command(f"lipo -info '{binary_path}'")
        if success:
            print(f"[LIPO] {binary_path}: {lipo_out}")
            
            # Check if the expected architecture is present
            if expected_arch == "x86_64" and "x86_64" in lipo_out:
                return True, "Architecture verified: x86_64"
            elif expected_arch == "arm64" and "arm64" in lipo_out:
                return True, "Architecture verified: arm64"
            elif "fat file" in lipo_out.lower():
                return True, f"Universal binary detected: {lipo_out}"
            else:
                return False, f"Expected {expected_arch} but got: {lipo_out}"
        else:
            print(f"[LIPO] Failed: {lipo_err}")
    
    # Fallback check using file command output
    if expected_arch == "x86_64" and ("x86_64" in stdout or "x86-64" in stdout):
        return True, "Architecture verified: x86_64 (via file command)"
    elif expected_arch == "arm64" and ("arm64" in stdout or "aarch64" in stdout):
        return True, "Architecture verified: arm64 (via file command)"
    
    return False, f"Architecture mismatch. Expected: {expected_arch}, Got: {stdout}"


def verify_app_bundle(app_path, expected_arch):
    """Verify the architecture of a macOS app bundle"""
    if not os.path.exists(app_path):
        return False, f"App bundle not found: {app_path}"
    
    print(f"[VERIFY] Checking app bundle: {app_path}")
    
    # Check main executable
    main_executable = os.path.join(app_path, "Contents", "MacOS", "eCan")
    if os.path.exists(main_executable):
        success, message = verify_binary_architecture(main_executable, expected_arch)
        if not success:
            return False, f"Main executable verification failed: {message}"
        print(f"[OK] Main executable: {message}")
    else:
        return False, f"Main executable not found: {main_executable}"
    
    # Check for Python executable in _internal
    python_executables = [
        os.path.join(app_path, "Contents", "MacOS", "_internal", "python"),
        os.path.join(app_path, "Contents", "Resources", "_internal", "python"),
    ]
    
    for python_exe in python_executables:
        if os.path.exists(python_exe):
            success, message = verify_binary_architecture(python_exe, expected_arch)
            if success:
                print(f"[OK] Python executable: {message}")
            else:
                print(f"[WARNING] Python executable issue: {message}")
            break
    
    return True, "App bundle architecture verification completed"


def verify_pkg_installer(pkg_path, expected_arch):
    """Verify the architecture of a PKG installer"""
    if not os.path.exists(pkg_path):
        return False, f"PKG installer not found: {pkg_path}"
    
    print(f"[VERIFY] Checking PKG installer: {pkg_path}")
    
    # Extract PKG contents to temporary directory for inspection
    import tempfile
    import shutil
    
    with tempfile.TemporaryDirectory() as temp_dir:
        # Use pkgutil to extract payload
        extract_cmd = f"pkgutil --expand '{pkg_path}' '{temp_dir}/extracted'"
        success, stdout, stderr = run_command(extract_cmd)
        
        if not success:
            return False, f"Failed to extract PKG: {stderr}"
        
        # Look for the app bundle in extracted contents
        extracted_path = os.path.join(temp_dir, "extracted")
        for root, dirs, files in os.walk(extracted_path):
            for dir_name in dirs:
                if dir_name.endswith(".app"):
                    app_path = os.path.join(root, dir_name)
                    return verify_app_bundle(app_path, expected_arch)
        
        return False, "No app bundle found in PKG contents"


def main():
    """Main verification function"""
    # Get expected architecture from environment
    expected_arch = os.getenv('PYINSTALLER_TARGET_ARCH') or os.getenv('TARGET_ARCH')
    build_arch = os.getenv('BUILD_ARCH')
    
    # Map build architecture to expected binary architecture
    if build_arch == "aarch64":
        expected_arch = "arm64"
    elif build_arch == "amd64":
        expected_arch = "x86_64"
    elif not expected_arch:
        expected_arch = "x86_64"  # Default
    
    print(f"[VERIFY] Expected architecture: {expected_arch}")
    print(f"[VERIFY] Build architecture: {build_arch}")
    print(f"[VERIFY] Current platform: {platform.platform()}")
    print(f"[VERIFY] Current machine: {platform.machine()}")
    
    # Check dist directory
    dist_dir = Path("dist")
    if not dist_dir.exists():
        print("[ERROR] dist directory not found")
        return 1
    
    # Look for app bundle
    app_bundle = dist_dir / "eCan.app"
    if app_bundle.exists():
        success, message = verify_app_bundle(str(app_bundle), expected_arch)
        if not success:
            print(f"[ERROR] App bundle verification failed: {message}")
            return 1
        print(f"[OK] {message}")
    
    # Look for PKG installer
    pkg_files = list(dist_dir.glob("*.pkg"))
    if pkg_files:
        for pkg_file in pkg_files:
            success, message = verify_pkg_installer(str(pkg_file), expected_arch)
            if not success:
                print(f"[ERROR] PKG verification failed: {message}")
                return 1
            print(f"[OK] {message}")
    
    print("[SUCCESS] Architecture verification completed successfully")
    return 0


if __name__ == "__main__":
    sys.exit(main())
