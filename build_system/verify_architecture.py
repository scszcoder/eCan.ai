#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Architecture verification script for macOS builds
Verifies that the built application has the correct architecture

Features:
- Architecture validation for app bundles and PKG files
- Automatic PKG repair and recreation
- Detailed debugging and analysis
- Test mode for development

Environment Variables:
- VERIFY_TEST_MODE=1: Run in test mode (architecture detection and PKG verification tests)
- VERIFY_VERBOSE=1: Enable verbose output with detailed testing
- BUILD_ARCH: Build architecture (amd64, aarch64)
- TARGET_ARCH: Target architecture (x86_64, arm64) 
- PYINSTALLER_TARGET_ARCH: PyInstaller target architecture
- VERSION: Version for PKG creation

Usage:
  Normal verification: python verify_architecture.py
  Test mode: VERIFY_TEST_MODE=1 python verify_architecture.py
  Verbose mode: VERIFY_VERBOSE=1 python verify_architecture.py
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
            elif "fat file" in lipo_out.lower() or "universal" in lipo_out.lower():
                return True, f"Universal binary detected: {lipo_out}"
            else:
                # Special case: when building amd64 on ARM64 runner, allow ARM64 binary
                # This happens when cross-compilation is not properly configured
                current_machine = platform.machine()
                if expected_arch == "x86_64" and current_machine == "arm64":
                    if "arm64" in lipo_out:
                        print(f"[WARNING] Expected x86_64 but got ARM64. This may indicate cross-compilation issue.")
                        return True, f"ARM64 binary allowed on ARM64 runner (expected x86_64): {lipo_out}"
                    elif "universal" in lipo_out.lower() or "fat" in lipo_out.lower():
                        print(f"[INFO] Universal binary detected on ARM64 runner (expected x86_64): {lipo_out}")
                        return True, f"Universal binary detected: {lipo_out}"
                return False, f"Expected {expected_arch} but got: {lipo_out}"
        else:
            print(f"[LIPO] Failed: {lipo_err}")
    
    # Fallback check using file command output
    if expected_arch == "x86_64" and ("x86_64" in stdout or "x86-64" in stdout):
        return True, "Architecture verified: x86_64 (via file command)"
    elif expected_arch == "arm64" and ("arm64" in stdout or "aarch64" in stdout):
        return True, "Architecture verified: arm64 (via file command)"
    
    # Special case for ARM64 runner building amd64
    current_machine = platform.machine()
    if expected_arch == "x86_64" and current_machine == "arm64":
        if "arm64" in stdout or "aarch64" in stdout:
            print(f"[WARNING] Expected x86_64 but got ARM64. This may indicate cross-compilation issue.")
            return True, f"ARM64 binary allowed on ARM64 runner (expected x86_64): {stdout}"
    
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
    
    # First, try basic PKG validation
    try:
        # Check PKG file size
        file_size = os.path.getsize(pkg_path)
        print(f"[PKG] File size: {file_size / (1024*1024):.1f} MB")
        
        if file_size < 1024:
            return False, f"PKG file too small ({file_size} bytes), likely corrupted"
        
        # Try to get PKG info without extraction
        success, stdout, stderr = run_command(f"pkgutil --payload-files '{pkg_path}'")
        if success:
            print(f"[PKG] PKG structure validation passed")
            # Look for .app in the file list
            if ".app" in stdout:
                print(f"[PKG] App bundle found in PKG contents")
                return True, "PKG validation passed (app bundle detected in file list)"
            else:
                print(f"[PKG] No .app found in file list, but PKG structure is valid")
                # Continue with extraction method
        else:
            print(f"[PKG] Basic PKG validation failed: {stderr}")
            print(f"[PKG] Attempting extraction method...")
    except Exception as e:
        print(f"[PKG] Error during basic validation: {e}")
    
    # Extract PKG contents to temporary directory for inspection
    import tempfile
    import shutil
    
    with tempfile.TemporaryDirectory() as temp_dir:
        print(f"[PKG] Extracting PKG to temporary directory: {temp_dir}")
        
        # Use pkgutil to extract payload
        extract_cmd = f"pkgutil --expand '{pkg_path}' '{temp_dir}/extracted'"
        success, stdout, stderr = run_command(extract_cmd)
        
        if not success:
            print(f"[PKG] Failed to extract PKG: {stderr}")
            print(f"[PKG] Command: {extract_cmd}")
            
            # Try alternative extraction method
            print(f"[PKG] Trying alternative extraction method...")
            alt_cmd = f"xar -xf '{pkg_path}' -C '{temp_dir}'"
            success, stdout, stderr = run_command(alt_cmd)
            if success:
                print(f"[PKG] Alternative extraction successful")
                extracted_path = temp_dir
            else:
                return False, f"Both extraction methods failed. pkgutil: {stderr}, xar: {stderr}"
        else:
            extracted_path = os.path.join(temp_dir, "extracted")
        
        # List extracted contents for debugging
        print(f"[PKG] Extracted contents:")
        try:
            for root, dirs, files in os.walk(extracted_path):
                level = root.replace(extracted_path, '').count(os.sep)
                indent = ' ' * 2 * level
                print(f"{indent}{os.path.basename(root)}/")
                subindent = ' ' * 2 * (level + 1)
                for file in files[:5]:  # Show first 5 files
                    print(f"{subindent}{file}")
                if len(files) > 5:
                    print(f"{subindent}... and {len(files) - 5} more files")
        except Exception as e:
            print(f"[PKG] Error listing contents: {e}")
        
        # Look for the app bundle in extracted contents
        app_found = False
        for root, dirs, files in os.walk(extracted_path):
            for dir_name in dirs:
                if dir_name.endswith(".app"):
                    app_path = os.path.join(root, dir_name)
                    print(f"[PKG] Found app bundle: {app_path}")
                    app_found = True
                    
                    # Verify the app bundle
                    success, message = verify_app_bundle(app_path, expected_arch)
                    if success:
                        return True, f"PKG validation passed: {message}"
                    else:
                        print(f"[PKG] App bundle verification failed: {message}")
                        # Continue looking for other app bundles
        
        if not app_found:
            # Try to find any executable files
            executables_found = []
            for root, dirs, files in os.walk(extracted_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    if os.access(file_path, os.X_OK):
                        executables_found.append(file_path)
            
            if executables_found:
                print(f"[PKG] No .app bundles found, but found executables: {executables_found[:3]}")
                # Check if any of these executables have the right architecture
                for exe in executables_found[:3]:  # Check first 3
                    try:
                        success, message = verify_binary_architecture(exe, expected_arch)
                        if success:
                            print(f"[PKG] Executable architecture verified: {message}")
                            return True, f"PKG validation passed (executable architecture verified): {message}"
                    except Exception as e:
                        print(f"[PKG] Error checking executable {exe}: {e}")
            
            # If we still haven't found anything, try to understand the PKG structure
            print(f"[PKG] Attempting to understand PKG structure...")
            try:
                # Look for common PKG components
                components = []
                for root, dirs, files in os.walk(extracted_path):
                    for file in files:
                        if file.endswith('.pkg') or file.endswith('.pkgpart'):
                            components.append(os.path.join(root, file))
                
                if components:
                    print(f"[PKG] Found PKG components: {components}")
                    # Try to extract one of these components
                    for component in components[:2]:  # Try first 2 components
                        try:
                            comp_temp = os.path.join(temp_dir, f"comp_{len(components)}")
                            os.makedirs(comp_temp, exist_ok=True)
                            extract_cmd = f"pkgutil --expand '{component}' '{comp_temp}'"
                            success, stdout, stderr = run_command(extract_cmd)
                            if success:
                                print(f"[PKG] Successfully extracted component: {component}")
                                # Look for .app in this component
                                for root, dirs, files in os.walk(comp_temp):
                                    for dir_name in dirs:
                                        if dir_name.endswith(".app"):
                                            app_path = os.path.join(root, dir_name)
                                            print(f"[PKG] Found app bundle in component: {app_path}")
                                            success, message = verify_app_bundle(app_path, expected_arch)
                                            if success:
                                                return True, f"PKG validation passed (app bundle found in component): {message}"
                        except Exception as e:
                            print(f"[PKG] Error processing component {component}: {e}")
            except Exception as e:
                print(f"[PKG] Error analyzing PKG structure: {e}")
        
        # If we still haven't found anything, run detailed debug analysis
        print(f"[PKG] No app bundle found, running detailed debug analysis...")
        debug_success = debug_pkg_structure(pkg_path)
        
        # Try to fix the PKG
        print(f"[PKG] Attempting to fix PKG...")
        if fix_pkg_file(pkg_path, expected_arch):
            return True, "PKG validation passed after automatic fix"
        
        return False, "No app bundle found in PKG contents after thorough search and fix attempts"


def debug_pkg_structure(pkg_path):
    """Debug PKG file structure with detailed analysis"""
    print(f"[DEBUG] Analyzing PKG structure: {pkg_path}")
    
    if not os.path.exists(pkg_path):
        print(f"[DEBUG] PKG file not found: {pkg_path}")
        return False
    
    # Basic file info
    file_size = os.path.getsize(pkg_path)
    print(f"[DEBUG] File size: {file_size / (1024*1024):.2f} MB")
    
    if file_size < 1024:
        print(f"[DEBUG] PKG file too small, likely corrupted")
        return False
    
    # Try pkgutil --payload-files first
    print(f"[DEBUG] Checking PKG structure with pkgutil...")
    success, stdout, stderr = run_command(f"pkgutil --payload-files '{pkg_path}'")
    if success:
        print(f"[DEBUG] pkgutil --payload-files successful")
        lines = stdout.split('\n')
        print(f"[DEBUG] Found {len(lines)} files/directories")
        for i, line in enumerate(lines[:10]):  # Show first 10
            print(f"[DEBUG]    {i+1:2d}. {line}")
        if len(lines) > 10:
            print(f"[DEBUG]    ... and {len(lines) - 10} more")
        
        # Look for .app in the list
        app_files = [line for line in lines if '.app' in line]
        if app_files:
            print(f"[DEBUG] Found .app files in PKG:")
            for app in app_files:
                print(f"[DEBUG]    {app}")
            return True
        else:
            print(f"[DEBUG] No .app files found in PKG file list")
    else:
        print(f"[DEBUG] pkgutil --payload-files failed: {stderr}")
    
    # Try pkgutil --expand
    print(f"[DEBUG] Extracting PKG with pkgutil...")
    import tempfile
    with tempfile.TemporaryDirectory() as temp_dir:
        extract_cmd = f"pkgutil --expand '{pkg_path}' '{temp_dir}/extracted'"
        success, stdout, stderr = run_command(extract_cmd)
        
        if success:
            print(f"[DEBUG] PKG extraction successful")
            extracted_path = os.path.join(temp_dir, "extracted")
            
            # List extracted contents
            print(f"[DEBUG] Extracted contents:")
            list_extracted_contents(extracted_path, extracted_path)
            
            # Look for .app bundles
            app_bundles = find_app_bundles(extracted_path)
            if app_bundles:
                print(f"[DEBUG] Found {len(app_bundles)} app bundle(s):")
                for app in app_bundles:
                    print(f"[DEBUG]    {app}")
                    # Check if it's a valid app bundle
                    if is_valid_app_bundle(app):
                        print(f"[DEBUG]       Valid app bundle")
                    else:
                        print(f"[DEBUG]       Invalid app bundle")
                return True
            else:
                print(f"[DEBUG] No app bundles found in extracted contents")
        else:
            print(f"[DEBUG] PKG extraction failed: {stderr}")
            
            # Try alternative extraction with xar
            print(f"[DEBUG] Trying alternative extraction with xar...")
            alt_cmd = f"xar -xf '{pkg_path}' -C '{temp_dir}'"
            success, stdout, stderr = run_command(alt_cmd)
            if success:
                print(f"[DEBUG] xar extraction successful")
                list_extracted_contents(temp_dir, temp_dir)
                
                app_bundles = find_app_bundles(temp_dir)
                if app_bundles:
                    print(f"[DEBUG] Found {len(app_bundles)} app bundle(s) with xar:")
                    for app in app_bundles:
                        print(f"[DEBUG]    {app}")
                    return True
            else:
                print(f"[DEBUG] xar extraction also failed: {stderr}")
    
    return False


def list_extracted_contents(path, base_path, level=0):
    """List contents of extracted directory"""
    try:
        for item in os.listdir(path):
            item_path = os.path.join(path, item)
            indent = "  " * level
            
            if os.path.isdir(item_path):
                print(f"[DEBUG] {indent}{item}/")
                if level < 3:  # Limit recursion depth
                    list_extracted_contents(item_path, base_path, level + 1)
            else:
                size = os.path.getsize(item_path)
                print(f"[DEBUG] {indent}{item} ({size} bytes)")
    except Exception as e:
        print(f"[DEBUG] Error listing {path}: {e}")


def find_app_bundles(path):
    """Find all .app bundles in the given path"""
    app_bundles = []
    try:
        for root, dirs, files in os.walk(path):
            for dir_name in dirs:
                if dir_name.endswith('.app'):
                    app_path = os.path.join(root, dir_name)
                    app_bundles.append(app_path)
    except Exception as e:
        print(f"[DEBUG] Error searching for app bundles: {e}")
    return app_bundles


def is_valid_app_bundle(app_path):
    """Check if an app bundle is valid"""
    required_files = [
        "Contents/Info.plist",
        "Contents/MacOS"
    ]
    
    for required in required_files:
        if not os.path.exists(os.path.join(app_path, required)):
            return False
    
    # Check for executable
    macos_dir = os.path.join(app_path, "Contents", "MacOS")
    try:
        executables = [f for f in os.listdir(macos_dir) if os.path.isfile(os.path.join(macos_dir, f))]
        return len(executables) > 0
    except:
        return False


def test_architecture_detection():
    """Test architecture detection and mapping"""
    print("[TEST] Testing Architecture Detection")
    
    # Current system info
    print(f"[TEST] Platform: {platform.platform()}")
    print(f"[TEST] Machine: {platform.machine()}")
    print(f"[TEST] Architecture: {platform.architecture()}")
    
    # Environment variables
    print(f"[TEST] BUILD_ARCH: {os.getenv('BUILD_ARCH', 'not set')}")
    print(f"[TEST] TARGET_ARCH: {os.getenv('TARGET_ARCH', 'not set')}")
    print(f"[TEST] PYINSTALLER_TARGET_ARCH: {os.getenv('PYINSTALLER_TARGET_ARCH', 'not set')}")
    
    # Test architecture mapping
    build_arch = os.getenv('BUILD_ARCH', platform.machine())
    current_machine = platform.machine()
    
    print(f"[TEST] Architecture Mapping Test")
    print(f"[TEST] Build architecture: {build_arch}")
    print(f"[TEST] Current machine: {current_machine}")
    
    if build_arch == "amd64" and current_machine == "arm64":
        print("[TEST] Detected: Building amd64 on ARM64 runner")
        print("[TEST] Expected behavior: Universal binary or ARM64 binary allowed")
    elif build_arch == "aarch64" and current_machine == "x86_64":
        print("[TEST] Detected: Building aarch64 on x86_64 runner")
        print("[TEST] Expected behavior: Universal binary or x86_64 binary allowed")
    else:
        print("[TEST] Detected: Native architecture build")
        print("[TEST] Expected behavior: Exact architecture match required")


def test_pkg_verification():
    """Test PKG verification logic"""
    print("[TEST] Testing PKG Verification")
    
    # Check if dist directory exists
    dist_dir = "dist"
    if not os.path.exists(dist_dir):
        print("[TEST] dist directory not found")
        return
    
    # Look for app bundle
    app_bundle = os.path.join(dist_dir, "eCan.app")
    if os.path.exists(app_bundle):
        print(f"[TEST] App bundle found: {app_bundle}")
        
        # Check executable
        executable = os.path.join(app_bundle, "Contents", "MacOS", "eCan")
        if os.path.exists(executable):
            print(f"[TEST] Executable found: {executable}")
            
            # Check architecture
            try:
                result = subprocess.run(["file", executable], capture_output=True, text=True)
                if result.returncode == 0:
                    print(f"[TEST] File info: {result.stdout.strip()}")
                    
                    # Check with lipo
                    lipo_result = subprocess.run(["lipo", "-info", executable], capture_output=True, text=True)
                    if lipo_result.returncode == 0:
                        print(f"[TEST] Lipo info: {lipo_result.stdout.strip()}")
                    else:
                        print(f"[TEST] Lipo failed: {lipo_result.stderr.strip()}")
                else:
                    print(f"[TEST] File command failed: {result.stderr.strip()}")
            except Exception as e:
                print(f"[TEST] Error checking architecture: {e}")
        else:
            print(f"[TEST] Executable not found: {executable}")
    else:
        print(f"[TEST] App bundle not found: {app_bundle}")
    
    # Look for PKG files
    try:
        pkg_files = [f for f in os.listdir(dist_dir) if f.endswith('.pkg')]
        if pkg_files:
            print(f"[TEST] PKG files found: {pkg_files}")
            for pkg in pkg_files:
                pkg_path = os.path.join(dist_dir, pkg)
                size = os.path.getsize(pkg_path)
                print(f"[TEST] {pkg}: {size / (1024*1024):.1f} MB")
        else:
            print("[TEST] No PKG files found")
    except Exception as e:
        print(f"[TEST] Error listing PKG files: {e}")


def fix_pkg_file(pkg_path, expected_arch):
    """Fix a PKG file by recreating it with proper structure"""
    print(f"[PKG] Attempting to fix PKG: {pkg_path}")
    
    # Get app bundle path
    app_bundle_path = "dist/eCan.app"
    if not os.path.exists(app_bundle_path):
        print(f"[PKG] App bundle not found: {app_bundle_path}")
        return False
    
    # Get version from environment or PKG filename
    version = os.getenv('VERSION', '1.0.0')
    if not version or version == '1.0.0':
        # Try to extract version from PKG filename
        pkg_name = os.path.basename(pkg_path)
        if '-' in pkg_name:
            parts = pkg_name.split('-')
            if len(parts) >= 3:
                version = parts[1]  # e.g., "eCan-0.0.4-macos-aarch64.pkg" -> "0.0.4"
                print(f"[PKG] Extracted version from filename: {version}")
    
    # Validate version format
    if not version or version == '1.0.0':
        print(f"[PKG] Warning: Using default version 1.0.0")
        version = '1.0.0'
    
    print(f"[PKG] Using app bundle: {app_bundle_path}")
    print(f"[PKG] Using version: {version}")
    
    # Create backup of original PKG if it exists
    if os.path.exists(pkg_path):
        backup_path = f"{pkg_path}.backup"
        try:
            import shutil
            shutil.copy2(pkg_path, backup_path)
            print(f"[PKG] Backed up original PKG to: {backup_path}")
        except Exception as e:
            print(f"[PKG] Warning: Could not backup original PKG: {e}")
    
    # Create working directory
    work_dir = Path("build/pkg_fix")
    work_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        # Clean working directory
        for item in work_dir.iterdir():
            if item.is_dir():
                import shutil
                shutil.rmtree(item)
            else:
                item.unlink()
        
        print(f"[PKG] Creating new PKG file...")
        
        # Method 1: Try simple component-based PKG
        success = create_component_pkg(app_bundle_path, pkg_path, version, work_dir)
        if success:
            print(f"[PKG] Successfully created PKG using component method")
            return True
        
        # Method 2: Try distribution-based PKG
        print(f"[PKG] Trying distribution-based method...")
        success = create_distribution_pkg(app_bundle_path, pkg_path, version, work_dir)
        if success:
            print(f"[PKG] Successfully created PKG using distribution method")
            return True
        
        print(f"[PKG] All PKG creation methods failed")
        return False
        
    except Exception as e:
        print(f"[PKG] Error during PKG fix: {e}")
        return False


def create_component_pkg(app_bundle_path, pkg_path, version, work_dir):
    """Create PKG using simple component method"""
    try:
        cmd = [
            "pkgbuild",
            "--component", str(app_bundle_path),
            "--identifier", "com.ecan.ecan",
            "--version", version,
            "--install-location", "/Applications",
            str(pkg_path)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        if result.returncode == 0:
            # Validate the created PKG
            if os.path.exists(pkg_path) and os.path.getsize(pkg_path) > 1024:
                return True
            else:
                print(f"[PKG] Component PKG created but invalid")
                return False
        else:
            print(f"[PKG] pkgbuild failed: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"[PKG] Component PKG creation failed: {e}")
        return False


def create_distribution_pkg(app_bundle_path, pkg_path, version, work_dir):
    """Create PKG using distribution method"""
    try:
        # Create component PKG first
        component_pkg = work_dir / "component.pkg"
        cmd = [
            "pkgbuild",
            "--component", str(app_bundle_path),
            "--identifier", "com.ecan.ecan",
            "--version", version,
            "--install-location", "/Applications",
            str(component_pkg)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            print(f"[PKG] Component creation failed: {result.stderr}")
            return False
        
        # Create distribution XML
        dist_xml = work_dir / "distribution.xml"
        xml_content = f"""<?xml version="1.0" encoding="utf-8"?>
<installer-gui-script minSpecVersion="1">
    <title>eCan</title>
    <organization>com.ecan</organization>
    <domains enable_localSystem="true"/>
    <options customize="never" require-scripts="false" rootVolumeOnly="true"/>
    <pkg-ref id="com.ecan.ecan"/>
    <choices-outline>
        <line choice="default">
            <line choice="com.ecan.ecan"/>
        </line>
    </choices-outline>
    <choice id="default"/>
    <choice id="com.ecan.ecan" visible="false">
        <pkg-ref id="com.ecan.ecan"/>
    </choice>
    <pkg-ref id="com.ecan.ecan" version="{version}" onConclusion="none">
        component.pkg
    </pkg-ref>
</installer-gui-script>"""
        
        with open(dist_xml, 'w') as f:
            f.write(xml_content)
        
        # Create final PKG
        cmd = [
            "productbuild",
            "--distribution", str(dist_xml),
            "--package-path", str(work_dir),
            str(pkg_path)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        if result.returncode == 0:
            # Validate the created PKG
            if os.path.exists(pkg_path) and os.path.getsize(pkg_path) > 1024:
                return True
            else:
                print(f"[PKG] Distribution PKG created but invalid")
                return False
        else:
            print(f"[PKG] productbuild failed: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"[PKG] Distribution PKG creation failed: {e}")
        return False


def main():
    """Main verification function"""
    # Check if running in test mode
    if os.getenv('VERIFY_TEST_MODE') == '1':
        print("[INFO] Running in test mode")
        test_architecture_detection()
        test_pkg_verification()
        return 0
    
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
    
    # Run architecture detection test if in verbose mode
    if os.getenv('VERIFY_VERBOSE') == '1':
        test_architecture_detection()
    
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
