#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Qt WebEngine macOS Framework Symlink Fixer for PyInstaller bundles

This module specifically addresses the QtWebEngineProcess path issue that occurs
when PyInstaller packages Qt WebEngine applications on macOS.

Root Cause Analysis:
===================
1. macOS Framework Structure vs Windows DLL Model:
   - Windows: Simple DLL loading with QtWebEngineProcess.exe as standalone executable
   - macOS: Complex framework with symlinks and nested app bundles

2. PyInstaller's Limitation:
   - Designed for cross-platform compatibility with unified file collection model
   - Cannot properly handle macOS framework symlink structures
   - Flattens symlinks during packaging, breaking framework integrity

3. Qt WebEngine Specificity:
   - More complex than regular Qt modules (contains nested app bundle)
   - Requires specific symlink structure for proper path resolution
   - Runtime expects: Framework/Helpers/QtWebEngineProcess.app
   - PyInstaller creates: Framework/Versions/Resources/Helpers/QtWebEngineProcess.app

Solution:
=========
Post-build framework structure reconstruction to create the expected symlink hierarchy.
"""

import os
import sys
import logging
from pathlib import Path
from typing import Optional


class QtFrameworkFixer:
    """Simplified Qt framework path fixer focused on QtWebEngine"""
    
    def __init__(self, bundle_path: Path, verbose: bool = False):
        """Initialize the Qt framework fixer"""
        self.bundle_path = Path(bundle_path)
        self.verbose = verbose
        self.logger = self._setup_logger()
        
    def _setup_logger(self) -> logging.Logger:
        """Setup logger for the fixer"""
        logger = logging.getLogger("QtFrameworkFixer")
        logger.setLevel(logging.DEBUG if self.verbose else logging.INFO)
        
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('[QT-FRAMEWORK-FIX] %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            
        return logger
    
    def fix_qt_webengine(self) -> bool:
        """Fix Qt WebEngine framework structure"""
        if sys.platform != 'darwin':
            self.logger.info("Skipping Qt framework fix (not macOS)")
            return True
            
        try:
            # Find QtWebEngineCore frameworks
            frameworks = list(self.bundle_path.rglob("QtWebEngineCore.framework"))
            
            if not frameworks:
                self.logger.info("No QtWebEngineCore frameworks found")
                return True
                
            success = True
            for framework in frameworks:
                self.logger.info(f"Fixing framework: {framework}")
                if not self._fix_framework_structure(framework):
                    success = False
                    
            return success
            
        except Exception as e:
            self.logger.error(f"Failed to fix Qt WebEngine: {e}")
            return False
    
    def _fix_framework_structure(self, framework_path: Path) -> bool:
        """Fix individual framework structure - minimal and precise"""
        try:
            versions_dir = framework_path / "Versions"
            if not versions_dir.exists():
                self.logger.debug(f"No Versions directory in {framework_path}")
                return True

            # Only look for the common PyInstaller misplaced location
            process_app = versions_dir / "Resources" / "Helpers" / "QtWebEngineProcess.app"
            if not process_app.exists():
                self.logger.debug(f"No QtWebEngineProcess.app found at expected PyInstaller location")
                return True

            self.logger.debug(f"Found QtWebEngineProcess.app at: {process_app}")

            # Ensure version directory A exists
            version_a = versions_dir / "A"
            if not version_a.exists():
                version_a.mkdir(exist_ok=True)
                self.logger.debug(f"Created version directory: {version_a}")

            # Ensure Current symlink exists
            current_link = versions_dir / "Current"
            if not current_link.exists():
                current_link.symlink_to("A")
                self.logger.debug(f"Created Current symlink: {current_link}")

            # Create only the necessary QtWebEngineProcess symlink
            expected_helpers = version_a / "Helpers"
            expected_process = expected_helpers / "QtWebEngineProcess.app"

            if not expected_process.exists():
                expected_helpers.mkdir(parents=True, exist_ok=True)
                relative_path = os.path.relpath(process_app, expected_helpers)
                expected_process.symlink_to(relative_path)
                self.logger.debug(f"Created QtWebEngineProcess symlink: {expected_process} -> {relative_path}")

            # Create only the required framework-level Helpers symlink
            helpers_link = framework_path / "Helpers"
            if not helpers_link.exists():
                try:
                    helpers_link.symlink_to("Versions/Current/Helpers")
                    self.logger.debug(f"Created Helpers symlink: {helpers_link}")
                except Exception as e:
                    self.logger.debug(f"Failed to create Helpers symlink: {e}")

            return True

        except Exception as e:
            self.logger.error(f"Failed to fix framework structure: {e}")
            return False


def main():
    """Command line interface"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Fix Qt framework paths in PyInstaller bundles")
    parser.add_argument("bundle_path", help="Path to the PyInstaller bundle")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose output")
    
    args = parser.parse_args()
    
    bundle_path = Path(args.bundle_path)
    if not bundle_path.exists():
        print(f"Error: Bundle path does not exist: {bundle_path}")
        sys.exit(1)
    
    fixer = QtFrameworkFixer(bundle_path, verbose=args.verbose)
    success = fixer.fix_qt_webengine()
    
    if success:
        print("Qt framework fixing completed successfully")
        sys.exit(0)
    else:
        print("Qt framework fixing failed")
        sys.exit(1)


if __name__ == "__main__":
    main()

