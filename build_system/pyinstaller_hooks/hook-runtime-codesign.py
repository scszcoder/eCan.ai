# -*- mode: python ; coding: utf-8 -*-
"""
Runtime hook for PyInstaller to handle codesign exclusions
This hook runs during the build process to ensure problematic files are treated as data
"""

import os
import sys
from pathlib import Path

def _is_codesign_excluded(file_path: str) -> bool:
    """Check if a file should be excluded from codesign"""
    # Convert to Path for easier manipulation
    path = Path(file_path)
    
    # Check if this is a Playwright browser file that should be excluded
    if 'ms-playwright' in str(path):
        # Check for Chromium.app and related files
        if any(pattern in str(path) for pattern in [
            'Chromium.app/Contents/MacOS/Chromium',
            'Chromium.app/Contents/Frameworks',
            'chrome',
            'chrome.exe'
        ]):
            return True
    
    return False

def _process_analysis_hook(analysis):
    """Process PyInstaller analysis to exclude problematic files from codesign"""
    if sys.platform != 'darwin':
        return  # Only apply on macOS
    
    print("[RUNTIME-HOOK] Processing analysis for codesign exclusions...")
    
    # Process binaries to move problematic files to datas
    excluded_binaries = []
    new_datas = []
    
    for binary in analysis.binaries:
        if _is_codesign_excluded(binary[0]):
            print(f"[RUNTIME-HOOK] Excluding from codesign: {binary[0]}")
            excluded_binaries.append(binary)
            # Add to datas instead
            new_datas.append(binary)
    
    # Remove excluded binaries and add to datas
    for binary in excluded_binaries:
        if binary in analysis.binaries:
            analysis.binaries.remove(binary)
    
    # Add new datas
    for data in new_datas:
        if data not in analysis.datas:
            analysis.datas.append(data)
    
    print(f"[RUNTIME-HOOK] Moved {len(excluded_binaries)} files from binaries to datas")
    print(f"[RUNTIME-HOOK] Analysis processing complete")

# This will be called by PyInstaller during the build process
try:
    # Try to get the current analysis object
    if 'analysis' in globals():
        _process_analysis_hook(analysis)
    else:
        print("[RUNTIME-HOOK] Analysis object not available, hook will be applied during build")
except Exception as e:
    print(f"[RUNTIME-HOOK] Error processing analysis: {e}")

print("[RUNTIME-HOOK] Runtime codesign hook loaded")
