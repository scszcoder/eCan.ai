#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build Environment Checker for eCan.ai
Checks if the build environment meets all requirements
"""

import sys
import os
import platform
import subprocess
import shutil
from pathlib import Path


class BuildEnvChecker:
    """Build environment checker"""
    
    def __init__(self, target_platform=None):
        self.target_platform = target_platform or self._detect_platform()
        self.errors = []
        self.warnings = []
        self.project_root = Path(__file__).parent.parent
        
    def _detect_platform(self):
        """Detect current platform"""
        system = platform.system().lower()
        if system == 'darwin':
            return 'macos'
        elif system == 'windows':
            return 'windows'
        elif system == 'linux':
            return 'linux'
        return system
    
    def _check_command(self, cmd, name=None, required=True):
        """Check if command is available"""
        name = name or cmd
        if shutil.which(cmd):
            try:
                result = subprocess.run([cmd, '--version'], 
                                      capture_output=True, 
                                      timeout=5)
                version = result.stdout.split('\n')[0] if result.stdout else result.stderr.split('\n')[0]
                print(f"   [OK] {name}: {version}")
                return True
            except Exception as e:
                print(f"   [OK] {name}: available (version check failed)")
                return True
        else:
            if required:
                print(f"   [ERROR] {name}: not found")
                self.errors.append(f"{name} is required but not found")
                return False
            else:
                print(f"   [WARNING] {name}: not found")
                self.warnings.append(f"{name} is optional but not found")
                return False
    
    def _check_python_package(self, package_name, import_name=None, required=True):
        """Check if Python package is installed"""
        import_name = import_name or package_name
        try:
            module = __import__(import_name)
            version = getattr(module, '__version__', 'unknown version')
            print(f"   [OK] {package_name}: {version}")
            return True
        except ImportError:
            if required:
                print(f"   [ERROR] {package_name}: not installed")
                self.errors.append(f"Python package '{package_name}' is required but not installed")
                return False
            else:
                print(f"   [WARNING] {package_name}: not installed")
                self.warnings.append(f"Python package '{package_name}' is optional but not installed")
                return False
    
    def check_basic_tools(self):
        """Check basic build tools"""
        print("\n[CHECK] Basic Build Tools:")
        self._check_command('git', 'Git')
        self._check_command('python', 'Python 3')
        self._check_command('pip', 'pip')
    
    def check_nodejs(self):
        """Check Node.js and npm"""
        print("\n[CHECK] Node.js Environment:")
        self._check_command('node', 'Node.js')
        self._check_command('npm', 'npm')
    
    def check_python_packages(self):
        """Check required Python packages"""
        print("\n[CHECK] Python Packages:")
        self._check_python_package('PyInstaller')
        self._check_python_package('PySide6')
        self._check_python_package('setuptools')
        self._check_python_package('wheel')
    
    def check_windows_tools(self):
        """Check Windows-specific build tools"""
        print("\n[CHECK] Windows Build Tools:")
        # Check for Inno Setup (Windows installer)
        innosetup_paths = [
            r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
            r"C:\Program Files\Inno Setup 6\ISCC.exe"
        ]
        
        found = False
        for path in innosetup_paths:
            if os.path.exists(path):
                print(f"   [OK] Inno Setup: found at {path}")
                found = True
                break
        
        if not found:
            print("   [ERROR] Inno Setup: not found")
            self.errors.append("Inno Setup is required for Windows builds")
    
    def check_macos_tools(self):
        """Check macOS-specific build tools"""
        print("\n[CHECK] macOS Build Tools:")
        # Check Xcode
        if shutil.which('xcodebuild'):
            try:
                result = subprocess.run(['xcodebuild', '-version'], 
                                      capture_output=True, 
                                      text=True, 
                                      timeout=5)
                version = result.stdout.split('\n')[0]
                version = result.stdout.split('\n')[0]
                print(f"   [OK] Xcode: {version}")
            except Exception as e:
                print("   [OK] Xcode: available")
        else:
            print("   [INFO] Xcode: not found")
            self.warnings.append("Xcode is recommended for macOS builds")
            
        # Check codesign
        self._check_command('codesign', 'codesign', required=False)
        self._check_command('pkgbuild', 'pkgbuild', required=True)
        self._check_command('productbuild', 'productbuild', required=True)
        
    def check_disk_space(self):
        """Check disk space"""
        print("\n[DISK] Disk Space:")
        try:
            if self.target_platform == 'windows':
                import ctypes
                free_bytes = ctypes.c_ulonglong(0)
                ctypes.windll.kernel32.GetDiskFreeSpaceExW(
                    ctypes.c_wchar_p(str(self.project_root)),
                    None, None,
                    ctypes.pointer(free_bytes)
                )
                free_gb = free_bytes.value / (1024**3)
                print(f"   Available: {free_gb:.1f} GB")
            else:
                stat = os.statvfs('/')
                free_gb = (stat.f_bavail * stat.f_frsize) / (1024**3)
                total_gb = (stat.f_blocks * stat.f_frsize) / (1024**3)
                used_gb = total_gb - free_gb
                used_percent = (used_gb / total_gb) * 100
                print(f"   Available: {free_gb:.1f} GB ({used_percent:.1f}% used)")
            
            # Warn if less than 10GB free
            if free_gb < 10:
                self.warnings.append(f"Low disk space: only {free_gb:.1f} GB available")
                print("   [WARNING] Low disk space warning")
        except Exception as e:
            print(f"   [INFO] Could not check disk space: {e}")
    
    def check_build_files(self):
        """Check required build files"""
        print("\n[CHECK] Build Files:")
        required_files = [
            ("setup.py", "Python package configuration"),
            ("pyproject.toml", "Build system requirements"),
            ("MANIFEST.in", "Package data files"),
            ("README.md", "Project documentation")
        ]
        
        for filename, description in required_files:
            path = self.project_root / filename
            if path.exists():
                print(f"   [OK] {filename}: found ({description})")
            else:
                print(f"   [WARNING] {filename}: not found ({description})")
                self.warnings.append(f"Build file '{filename}' is missing")
    
    
    def check_frontend_files(self):
        """Check frontend build files"""
        print("\n[CHECK] Frontend Files:")
        frontend_dir = self.project_root / "frontend"
        
        if frontend_dir.exists():
            print("   [OK] Frontend directory: found")
            
            # Check package.json
            package_json = frontend_dir / "package.json"
            if package_json.exists():
                print("   [OK] package.json: found")
            else:
                print("   [WARNING] package.json: not found")
                self.warnings.append("Frontend package.json is missing")
                
            # Check node_modules
            node_modules = frontend_dir / "node_modules"
            if node_modules.exists():
                print("   [OK] node_modules: found")
            else:
                print("   [WARNING] node_modules: not found (run 'npm install' in frontend directory)")
                self.warnings.append("Frontend dependencies not installed")
        else:
            print("   [INFO] Frontend directory: not found (skipping frontend checks)")
    
    def run_all_checks(self):
        """Run all environment checks and return status code"""
        print("=" * 70)
        print("[CHECK] Starting Build Environment Check")
        print("=" * 70)
        
        # Run all check methods
        self.check_basic_tools()
        self.check_nodejs()
        self.check_python_packages()
        
        # Platform-specific checks
        if self.target_platform == 'windows':
            self.check_windows_tools()
        elif self.target_platform == 'macos':
            self.check_macos_tools()
        
        # Additional checks
        self.check_build_files()
        self.check_frontend_files()
        self.check_disk_space()
        
        # Print summary
        print("\n" + "=" * 70)
        print("[SUMMARY] Check Results:")
        print("=" * 70)
        
        if self.errors:
            print(f"\n[ERROR] Errors ({len(self.errors)}):")
            for error in self.errors:
                print(f"   [ERROR] {error}")
                
        if self.warnings:
            print(f"\n[WARNING] Warnings ({len(self.warnings)}):")
            for warning in self.warnings:
                print(f"   [WARNING] {warning}")
        
        if not self.errors and not self.warnings:
            print("\n[SUCCESS] All checks passed! Build environment is ready.")
            return 0
        elif not self.errors:
            print(f"\n[SUCCESS] All required checks passed (with {len(self.warnings)} warnings)")
            return 0
        else:
            print(f"\n[FAILED] Build environment check failed with {len(self.errors)} errors")
            return 1


def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Check eCan.ai build environment',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        '--platform',
        choices=['windows', 'macos', 'linux'],
        help='Target platform (auto-detected if not specified)'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Show verbose output'
    )
    
    args = parser.parse_args()
    
    checker = BuildEnvChecker(target_platform=args.platform)
    exit_code = checker.run_all_checks()
    
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
