#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PKG Installer Test Script
Tests the PKG installer functionality and verifies installation
"""

import os
import sys
import subprocess
import tempfile
import shutil
from pathlib import Path
from typing import Optional, Dict, Any


class PKGInstallerTester:
    """Test PKG installer functionality"""
    
    def __init__(self, pkg_file: Path):
        self.pkg_file = pkg_file
        self.test_results = {}
        
    def run_all_tests(self) -> Dict[str, Any]:
        """Run all PKG installer tests"""
        print(f"[TEST] Testing PKG installer: {self.pkg_file}")
        print("=" * 60)
        
        tests = [
            ("Package Integrity", self.test_package_integrity),
            ("Package Contents", self.test_package_contents),
            ("Installation Simulation", self.test_installation_simulation),
            ("Launch Services Registration", self.test_launch_services_registration)
        ]
        
        for test_name, test_func in tests:
            print(f"\n[TEST] Running: {test_name}")
            try:
                result = test_func()
                self.test_results[test_name] = {
                    "status": "PASS" if result else "FAIL",
                    "details": result if isinstance(result, dict) else {}
                }
                status = "✓ PASS" if result else "✗ FAIL"
                print(f"[TEST] {test_name}: {status}")
            except Exception as e:
                self.test_results[test_name] = {
                    "status": "ERROR",
                    "error": str(e)
                }
                print(f"[TEST] {test_name}: ✗ ERROR - {e}")
        
        self._print_summary()
        return self.test_results
    
    def test_package_integrity(self) -> bool:
        """Test package integrity using pkgutil"""
        try:
            # Check if package can be read
            cmd = ["pkgutil", "--check-signature", str(self.pkg_file)]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            # For unsigned packages, we expect a specific error
            if result.returncode != 0:
                if "no signature" in result.stderr.lower():
                    print("[TEST] Package is unsigned (expected)")
                    return True
                else:
                    print(f"[TEST] Unexpected signature error: {result.stderr}")
                    return False
            else:
                print("[TEST] Package signature verified")
                return True
                
        except Exception as e:
            print(f"[TEST] Package integrity test failed: {e}")
            return False
    
    def test_package_contents(self) -> bool:
        """Test package contents structure"""
        try:
            # List package files
            cmd = ["pkgutil", "--files", str(self.pkg_file)]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode != 0:
                print(f"[TEST] Failed to list package files: {result.stderr}")
                return False
            
            files = result.stdout.strip().split('\n')
            
            # Check for essential app bundle structure
            essential_patterns = [
                "Applications/eCan.app/Contents/Info.plist",
                "Applications/eCan.app/Contents/MacOS/eCan",
                "Applications/eCan.app/Contents/Resources/"
            ]
            
            found_patterns = []
            for pattern in essential_patterns:
                found = any(pattern in f for f in files)
                found_patterns.append(found)
                if found:
                    print(f"[TEST] ✓ Found: {pattern}")
                else:
                    print(f"[TEST] ✗ Missing: {pattern}")
            
            return all(found_patterns)
            
        except Exception as e:
            print(f"[TEST] Package contents test failed: {e}")
            return False
    
    def test_installation_simulation(self) -> bool:
        """Simulate installation to a temporary directory"""
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                
                print(f"[TEST] Simulating installation to: {temp_path}")
                
                # Extract package to temporary directory
                cmd = ["pkgutil", "--expand", str(self.pkg_file), str(temp_path / "expanded")]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                
                if result.returncode != 0:
                    print(f"[TEST] Failed to expand package: {result.stderr}")
                    return False
                
                expanded_dir = temp_path / "expanded"
                if not expanded_dir.exists():
                    print("[TEST] Expanded directory not created")
                    return False
                
                # Check for component packages
                component_pkgs = list(expanded_dir.glob("*.pkg"))
                if not component_pkgs:
                    print("[TEST] No component packages found")
                    return False
                
                print(f"[TEST] ✓ Found {len(component_pkgs)} component package(s)")
                
                # Check for scripts
                scripts_dir = expanded_dir / component_pkgs[0].stem / "Scripts"
                if scripts_dir.exists():
                    scripts = list(scripts_dir.glob("*"))
                    print(f"[TEST] ✓ Found {len(scripts)} installation script(s)")
                    
                    # Check for postinstall script
                    postinstall = scripts_dir / "postinstall"
                    if postinstall.exists():
                        print("[TEST] ✓ Postinstall script found")
                        
                        # Check script content
                        with open(postinstall, 'r') as f:
                            content = f.read()
                            if "lsregister" in content:
                                print("[TEST] ✓ Launch Services registration found in postinstall")
                            else:
                                print("[TEST] ⚠ Launch Services registration not found in postinstall")
                    else:
                        print("[TEST] ⚠ Postinstall script not found")
                else:
                    print("[TEST] ⚠ No installation scripts found")
                
                return True
                
        except Exception as e:
            print(f"[TEST] Installation simulation failed: {e}")
            return False
    
    def test_launch_services_registration(self) -> bool:
        """Test Launch Services registration logic"""
        try:
            # This test checks if the postinstall script contains proper Launch Services commands
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                
                # Extract package
                cmd = ["pkgutil", "--expand", str(self.pkg_file), str(temp_path / "expanded")]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                
                if result.returncode != 0:
                    return False
                
                expanded_dir = temp_path / "expanded"
                component_pkgs = list(expanded_dir.glob("*.pkg"))
                
                if not component_pkgs:
                    return False
                
                scripts_dir = expanded_dir / component_pkgs[0].stem / "Scripts"
                postinstall = scripts_dir / "postinstall"
                
                if not postinstall.exists():
                    print("[TEST] ⚠ No postinstall script to test")
                    return False
                
                with open(postinstall, 'r') as f:
                    content = f.read()
                
                # Check for essential Launch Services commands
                required_commands = [
                    "lsregister -f",  # Register app
                    "defaults write com.apple.dock ResetLaunchPad"  # Gentle Launchpad refresh
                ]
                
                all_found = True
                for cmd in required_commands:
                    if cmd in content:
                        print(f"[TEST] ✓ Found command: {cmd}")
                    else:
                        print(f"[TEST] ✗ Missing command: {cmd}")
                        all_found = False
                
                return all_found
                
        except Exception as e:
            print(f"[TEST] Launch Services test failed: {e}")
            return False
    
    def _print_summary(self):
        """Print test summary"""
        print("\n" + "=" * 60)
        print("[TEST] SUMMARY")
        print("=" * 60)
        
        total_tests = len(self.test_results)
        passed_tests = sum(1 for r in self.test_results.values() if r["status"] == "PASS")
        failed_tests = sum(1 for r in self.test_results.values() if r["status"] == "FAIL")
        error_tests = sum(1 for r in self.test_results.values() if r["status"] == "ERROR")
        
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {passed_tests}")
        print(f"Failed: {failed_tests}")
        print(f"Errors: {error_tests}")
        
        if passed_tests == total_tests:
            print("\n🎉 All tests passed! PKG installer should work correctly.")
        else:
            print(f"\n⚠️  {failed_tests + error_tests} test(s) failed. Review the issues above.")
        
        print("=" * 60)


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Test PKG installer")
    parser.add_argument("pkg_file", help="Path to PKG file to test")
    
    args = parser.parse_args()
    
    pkg_file = Path(args.pkg_file)
    if not pkg_file.exists():
        print(f"[ERROR] PKG file not found: {pkg_file}")
        return 1
    
    if not pkg_file.suffix.lower() == '.pkg':
        print(f"[ERROR] File is not a PKG: {pkg_file}")
        return 1
    
    tester = PKGInstallerTester(pkg_file)
    results = tester.run_all_tests()
    
    # Return exit code based on results
    failed_count = sum(1 for r in results.values() if r["status"] in ["FAIL", "ERROR"])
    return 1 if failed_count > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
