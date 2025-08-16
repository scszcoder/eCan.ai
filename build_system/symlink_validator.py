#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Symlink validation utilities for macOS builds
Ensures critical symlinks are preserved during the build process
"""

import os
import sys
from pathlib import Path
from typing import List, Dict, Tuple, Optional

try:
    from .platform_handler import platform_handler
except ImportError:
    # Handle case when imported directly
    import platform as _platform
    class MockPlatformHandler:
        @property
        def is_macos(self):
            return _platform.system() == "Darwin"
    platform_handler = MockPlatformHandler()


class SymlinkValidator:
    """Validates and reports on symlink preservation in macOS builds"""
    
    def __init__(self, app_bundle_path: Optional[Path] = None):
        self.app_bundle_path = app_bundle_path
        self.issues = []
        self.checked_paths = []
        
    def validate_app_bundle(self, app_bundle_path: Path) -> Dict[str, any]:
        """Validate symlinks in macOS app bundle"""
        if not platform_handler.is_macos:
            return {"status": "skipped", "reason": "Not running on macOS"}
            
        if not app_bundle_path.exists():
            return {"status": "error", "reason": f"App bundle not found: {app_bundle_path}"}
            
        self.app_bundle_path = app_bundle_path
        self.issues = []
        self.checked_paths = []
        
        result = {
            "status": "success",
            "app_bundle": str(app_bundle_path),
            "issues": [],
            "checked_paths": [],
            "symlinks_found": [],
            "broken_symlinks": [],
            "critical_issues": []
        }
        
        try:
            # Check QtWebEngine symlinks
            self._check_qtwebengine_symlinks(result)
            
            # Check Playwright symlinks
            self._check_playwright_symlinks(result)
            
            # Check framework symlinks
            self._check_framework_symlinks(result)
            
            # Check for broken symlinks
            self._check_broken_symlinks(result)
            
            result["issues"] = self.issues
            result["checked_paths"] = [str(p) for p in self.checked_paths]
            
            if result["critical_issues"]:
                result["status"] = "warning"
                
        except Exception as e:
            result["status"] = "error"
            result["reason"] = str(e)
            
        return result
        
    def _check_qtwebengine_symlinks(self, result: Dict) -> None:
        """Check QtWebEngine framework symlinks"""
        frameworks_dir = self.app_bundle_path / "Contents" / "Frameworks"
        if not frameworks_dir.exists():
            return
            
        qtwebengine_framework = frameworks_dir / "QtWebEngineCore.framework"
        if qtwebengine_framework.exists():
            self.checked_paths.append(qtwebengine_framework)
            
            # Check Versions/Current symlink
            current_link = qtwebengine_framework / "Versions" / "Current"
            if current_link.exists():
                if current_link.is_symlink():
                    result["symlinks_found"].append(str(current_link))
                    target = current_link.readlink()
                    if not (current_link.parent / target).exists():
                        result["broken_symlinks"].append(str(current_link))
                        result["critical_issues"].append(f"Broken QtWebEngine Current symlink: {current_link}")
                else:
                    result["critical_issues"].append(f"QtWebEngine Current should be symlink: {current_link}")
                    
            # Check framework root symlinks
            for item in ["QtWebEngineCore", "Resources", "Helpers"]:
                item_path = qtwebengine_framework / item
                if item_path.exists() and item_path.is_symlink():
                    result["symlinks_found"].append(str(item_path))
                    
    def _check_playwright_symlinks(self, result: Dict) -> None:
        """Check Playwright browser symlinks"""
        # Check in Contents/Resources for third_party
        resources_dir = self.app_bundle_path / "Contents" / "Resources"
        playwright_paths = [
            resources_dir / "third_party" / "ms-playwright",
            resources_dir / "ms-playwright"
        ]
        
        for playwright_dir in playwright_paths:
            if playwright_dir.exists():
                self.checked_paths.append(playwright_dir)
                self._scan_directory_symlinks(playwright_dir, result, "Playwright")
                
    def _check_framework_symlinks(self, result: Dict) -> None:
        """Check all framework symlinks"""
        frameworks_dir = self.app_bundle_path / "Contents" / "Frameworks"
        if not frameworks_dir.exists():
            return
            
        for framework in frameworks_dir.glob("*.framework"):
            if framework.is_dir():
                self.checked_paths.append(framework)
                self._scan_framework_symlinks(framework, result)
                
    def _scan_framework_symlinks(self, framework_path: Path, result: Dict) -> None:
        """Scan a single framework for symlinks"""
        framework_name = framework_path.name
        
        # Check Versions/Current
        versions_dir = framework_path / "Versions"
        if versions_dir.exists():
            current_link = versions_dir / "Current"
            if current_link.exists():
                if current_link.is_symlink():
                    result["symlinks_found"].append(str(current_link))
                    # Verify target exists
                    try:
                        target = current_link.readlink()
                        if not (current_link.parent / target).exists():
                            result["broken_symlinks"].append(str(current_link))
                    except OSError:
                        result["broken_symlinks"].append(str(current_link))
                        
        # Check root level symlinks in framework
        for item in framework_path.iterdir():
            if item.is_symlink():
                result["symlinks_found"].append(str(item))
                try:
                    target = item.readlink()
                    # Check if target exists (relative to symlink location)
                    if not (item.parent / target).exists():
                        result["broken_symlinks"].append(str(item))
                except OSError:
                    result["broken_symlinks"].append(str(item))
                    
    def _scan_directory_symlinks(self, directory: Path, result: Dict, context: str = "") -> None:
        """Recursively scan directory for symlinks"""
        try:
            for item in directory.rglob("*"):
                if item.is_symlink():
                    result["symlinks_found"].append(str(item))
                    try:
                        target = item.readlink()
                        # For relative symlinks, check relative to symlink location
                        if not target.is_absolute():
                            target_path = item.parent / target
                        else:
                            target_path = target
                            
                        if not target_path.exists():
                            result["broken_symlinks"].append(str(item))
                            if context:
                                result["critical_issues"].append(f"Broken {context} symlink: {item}")
                    except OSError as e:
                        result["broken_symlinks"].append(str(item))
                        if context:
                            result["critical_issues"].append(f"Cannot read {context} symlink: {item} ({e})")
        except Exception as e:
            self.issues.append(f"Error scanning {directory}: {e}")
            
    def _check_broken_symlinks(self, result: Dict) -> None:
        """Final check for any broken symlinks"""
        if result["broken_symlinks"]:
            result["critical_issues"].extend([
                f"Found {len(result['broken_symlinks'])} broken symlinks",
                "This may cause runtime issues on macOS"
            ])
            
    def print_validation_report(self, result: Dict) -> None:
        """Print a formatted validation report"""
        print("\n" + "="*60)
        print("SYMLINK VALIDATION REPORT")
        print("="*60)
        
        print(f"Status: {result['status'].upper()}")
        print(f"App Bundle: {result.get('app_bundle', 'N/A')}")
        print(f"Checked Paths: {len(result.get('checked_paths', []))}")
        print(f"Symlinks Found: {len(result.get('symlinks_found', []))}")
        print(f"Broken Symlinks: {len(result.get('broken_symlinks', []))}")
        
        if result.get("critical_issues"):
            print(f"\n[!] CRITICAL ISSUES ({len(result['critical_issues'])}):")
            for issue in result["critical_issues"]:
                print(f"  - {issue}")

        if result.get("broken_symlinks"):
            print(f"\n[X] BROKEN SYMLINKS ({len(result['broken_symlinks'])}):")
            for symlink in result["broken_symlinks"][:10]:  # Show first 10
                print(f"  - {symlink}")
            if len(result["broken_symlinks"]) > 10:
                print(f"  ... and {len(result['broken_symlinks']) - 10} more")

        if result.get("issues"):
            print(f"\n[i] OTHER ISSUES ({len(result['issues'])}):")
            for issue in result["issues"]:
                print(f"  - {issue}")
                
        print("\n" + "="*60)
        
        # Recommendations
        if result["status"] == "warning" or result.get("broken_symlinks"):
            print("RECOMMENDATIONS:")
            print("- Verify PyInstaller is using symlinks=True in copytree operations")
            print("- Check that codesign exclusions are properly applied")
            print("- Consider using --preserve-symlinks flag if available")
            print("="*60)


# Global validator instance
symlink_validator = SymlinkValidator()
