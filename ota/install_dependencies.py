#!/usr/bin/env python3
"""
OTA Dependencies Installation Script（示例/占位）

This script helps install the correct dependencies for OTA functionality
on different platforms.

注意：此脚本为示例代码，建议使用主构建系统的依赖管理功能
"""

import os
import sys
import platform
import subprocess
import urllib.request
import zipfile
import shutil
from pathlib import Path


def get_platform():
    """Get the current platform"""
    system = platform.system()
    if system == "Darwin":
        return "macos"
    elif system == "Windows":
        return "windows"
    elif system == "Linux":
        return "linux"
    else:
        return "unknown"


def install_python_dependencies():
    """Install Python dependencies"""
    print("Installing Python dependencies...")
    
    current_platform = get_platform()
    
    if current_platform == "windows":
        requirements_file = "requirements-windows.txt"
    elif current_platform == "macos":
        requirements_file = "requirements-macos.txt"
    else:
        requirements_file = "requirements-base.txt"
    
    try:
        subprocess.run([
            sys.executable, "-m", "pip", "install", "-r", requirements_file
        ], check=True)
        print(f"✓ Python dependencies installed from {requirements_file}")
    except subprocess.CalledProcessError as e:
        print(f"✗ Failed to install Python dependencies: {e}")
        return False
    
    return True


def install_sparkle_macos():
    """Install Sparkle framework on macOS"""
    print("Installing Sparkle framework...")
    
    # Check if Homebrew is available
    try:
        subprocess.run(["brew", "--version"], check=True, capture_output=True)
        homebrew_available = True
    except (subprocess.CalledProcessError, FileNotFoundError):
        homebrew_available = False
    
    if homebrew_available:
        try:
            subprocess.run(["brew", "install", "sparkle"], check=True)
            print("✓ Sparkle installed via Homebrew")
            return True
        except subprocess.CalledProcessError:
            print("✗ Failed to install Sparkle via Homebrew")
    
    print("Homebrew not available or installation failed.")
    print("Please install Sparkle manually:")
    print("1. Download from: https://github.com/sparkle-project/Sparkle/releases")
    print("2. Extract and copy Sparkle.framework to /Library/Frameworks/")
    print("3. See platforms/SPARKLE_SETUP.md for detailed instructions")
    
    return False


def install_winsparkle_windows():
    """Install winSparkle on Windows"""
    print("Installing winSparkle...")
    
    # Create directories
    app_dir = Path.cwd()
    lib_dir = app_dir / "lib"
    lib_dir.mkdir(exist_ok=True)
    
    # Download winSparkle
    winsparkle_url = "https://github.com/vslavik/winsparkle/releases/download/v0.8.0/winsparkle-0.8.0.zip"
    zip_path = app_dir / "winsparkle.zip"
    
    try:
        print("Downloading winSparkle...")
        urllib.request.urlretrieve(winsparkle_url, zip_path)
        
        print("Extracting winSparkle...")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(app_dir / "winsparkle_temp")
        
        # Copy DLL to lib directory
        temp_dir = app_dir / "winsparkle_temp"
        dll_files = list(temp_dir.glob("**/winsparkle.dll"))
        
        if dll_files:
            shutil.copy2(dll_files[0], lib_dir / "winsparkle.dll")
            print(f"✓ winSparkle DLL copied to {lib_dir / 'winsparkle.dll'}")
        else:
            print("✗ winSparkle DLL not found in downloaded archive")
            return False
        
        # Cleanup
        zip_path.unlink()
        shutil.rmtree(temp_dir)
        
        return True
        
    except Exception as e:
        print(f"✗ Failed to install winSparkle: {e}")
        print("Please install winSparkle manually:")
        print("1. Download from: https://github.com/vslavik/winsparkle/releases")
        print("2. Extract and copy winsparkle.dll to your application directory")
        print("3. See platforms/WINSPARKLE_SETUP.md for detailed instructions")
        
        return False


def verify_installation():
    """Verify that OTA dependencies are properly installed"""
    print("\nVerifying installation...")
    
    try:
        # Test OTA import
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from ota import OTAUpdater
        
        updater = OTAUpdater()
        status = updater.get_status()
        
        print(f"✓ OTA system initialized")
        print(f"  Platform: {status['platform']}")
        print(f"  App version: {status['app_version']}")
        
        # Test platform-specific components
        current_platform = get_platform()
        
        if current_platform == "macos":
            if hasattr(updater.platform_updater, '_find_sparkle_framework'):
                framework_path = updater.platform_updater._find_sparkle_framework()
                if framework_path:
                    print(f"✓ Sparkle framework found at: {framework_path}")
                else:
                    print("⚠ Sparkle framework not found - will use generic updates")
        
        elif current_platform == "windows":
            if hasattr(updater.platform_updater, '_find_winsparkle_dll'):
                dll_path = updater.platform_updater._find_winsparkle_dll()
                if dll_path:
                    print(f"✓ winSparkle DLL found at: {dll_path}")
                else:
                    print("⚠ winSparkle DLL not found - will use generic updates")
        
        print("✓ Installation verification completed")
        return True
        
    except Exception as e:
        print(f"✗ Installation verification failed: {e}")
        return False


def main():
    """Main installation function"""
    print("ECBot OTA Dependencies Installation")
    print("=" * 40)
    
    current_platform = get_platform()
    print(f"Detected platform: {current_platform}")
    
    if current_platform == "unknown":
        print("✗ Unsupported platform")
        return 1
    
    # Install Python dependencies
    if not install_python_dependencies():
        return 1
    
    # Install platform-specific components
    if current_platform == "macos":
        install_sparkle_macos()
    elif current_platform == "windows":
        install_winsparkle_windows()
    else:
        print("✓ No additional dependencies needed for Linux")
    
    # Verify installation
    if verify_installation():
        print("\n🎉 Installation completed successfully!")
        print("\nNext steps:")
        print("1. Configure your update server URL")
        print("2. Set up digital signing keys")
        print("3. Test the update functionality")
        return 0
    else:
        print("\n❌ Installation completed with warnings")
        print("Check the messages above and refer to the setup guides:")
        print("- macOS: platforms/SPARKLE_SETUP.md")
        print("- Windows: platforms/WINSPARKLE_SETUP.md")
        return 1


if __name__ == "__main__":
    sys.exit(main())
