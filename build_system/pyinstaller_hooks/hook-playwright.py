# -*- coding: utf-8 -*-
"""
PyInstaller hook for playwright
Handles Playwright browser binaries collection
"""

import os
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_data_files

print("[HOOK] playwright hook executing...")

# Note: collect_all('playwright') is handled by build_config.json
# This hook only collects browser binaries that are not part of the Python package

# Initialize collections
datas = []
binaries = []
hiddenimports = []

# Collect Playwright browser binaries
try:
    import playwright
    playwright_path = Path(playwright.__file__).parent
    
    # Look for ms-playwright directory in common locations
    ms_playwright_paths = []
    
    # Check in playwright package directory
    package_ms_playwright = playwright_path / 'ms-playwright'
    if package_ms_playwright.exists():
        ms_playwright_paths.append(package_ms_playwright)
    
    # Check in user home directory (handle symlink)
    home_ms_playwright = Path.home() / '.cache' / 'ms-playwright'
    if home_ms_playwright.exists():
        # Resolve symlink to get the actual path
        if home_ms_playwright.is_symlink():
            actual_path = home_ms_playwright.resolve()
            print(f"[HOOK] Resolved symlink: {home_ms_playwright} -> {actual_path}")
            ms_playwright_paths.append(actual_path)
        else:
            ms_playwright_paths.append(home_ms_playwright)
    
    # Check in system cache directory
    system_ms_playwright = Path('/usr/local/share/ms-playwright')
    if system_ms_playwright.exists():
        ms_playwright_paths.append(system_ms_playwright)
    
    # Platform-specific paths (only if not already found in user cache)
    if sys.platform == 'darwin' and not any('Library/Application Support/eCan' in str(p) for p in ms_playwright_paths):
        # macOS - check multiple possible locations
        mac_paths = [
            Path('/opt/homebrew/share/ms-playwright'),
            Path('/usr/local/share/ms-playwright'),
        ]
        
        for mac_path in mac_paths:
            if mac_path.exists():
                # Resolve symlinks for macOS paths
                if mac_path.is_symlink():
                    actual_path = mac_path.resolve()
                    print(f"[HOOK] macOS: Resolved symlink: {mac_path} -> {actual_path}")
                    ms_playwright_paths.append(actual_path)
                else:
                    ms_playwright_paths.append(mac_path)
                print(f"[HOOK] macOS: Found ms-playwright at: {mac_path}")
                break  # Use the first found location
    elif sys.platform == 'win32':
        # Windows
        win_ms_playwright = Path(os.environ.get('LOCALAPPDATA', '')) / 'ms-playwright'
        if win_ms_playwright.exists():
            ms_playwright_paths.append(win_ms_playwright)
    else:
        # Linux
        linux_ms_playwright = Path('/usr/share/ms-playwright')
        if linux_ms_playwright.exists():
            ms_playwright_paths.append(linux_ms_playwright)
    
    # Collect browser binaries from found paths
    for ms_playwright_path in ms_playwright_paths:
        print(f"[HOOK] Found ms-playwright at: {ms_playwright_path}")
        
        # Look for chromium browsers
        chromium_patterns = [
            'chromium-*/chrome-mac/Chromium.app',
            'chromium-*/chrome-win/chrome.exe',
            'chromium-*/chrome-win/chrome',
            'chromium-*/chrome-linux/chrome',
        ]
        
        for pattern in chromium_patterns:
            for browser_path in ms_playwright_path.glob(pattern):
                if browser_path.exists():
                    # Determine destination path
                    if sys.platform == 'darwin' and browser_path.suffix == '.app':
                        dest_path = f"ms-playwright/{browser_path.relative_to(ms_playwright_path)}"
                    elif sys.platform == 'win32' and browser_path.suffix == '.exe':
                        dest_path = f"ms-playwright/{browser_path.relative_to(ms_playwright_path)}"
                    else:
                        dest_path = f"ms-playwright/{browser_path.relative_to(ms_playwright_path)}"
                    
                    datas.append((str(browser_path), dest_path))
                    print(f"[HOOK] Added Playwright browser: {browser_path} -> {dest_path}")
        
        # Also collect the entire ms-playwright directory structure
        if ms_playwright_path.exists():
            # Check if we already collected this path (avoid duplicates from symlinks)
            path_str = str(ms_playwright_path.resolve())  # Resolve symlinks for comparison
            if not any(str(Path(p[0]).resolve()) == path_str for p in datas):
                datas.append((str(ms_playwright_path), 'ms-playwright'))
                print(f"[HOOK] Added entire ms-playwright directory: {ms_playwright_path}")
                break  # Only add from the first found location
            else:
                print(f"[HOOK] Skipped duplicate ms-playwright path: {ms_playwright_path}")
    
    if not ms_playwright_paths:
        print("[HOOK] Warning: No ms-playwright directory found")
        print("[HOOK] You may need to run 'playwright install' first")
        
except ImportError:
    print("[HOOK] Warning: playwright not available")

print(f"[HOOK] playwright hook completed:")
print(f"  - Hidden imports: {len(hiddenimports)} modules")
print(f"  - Data files: {len(datas)} files")
print(f"  - Binary files: {len(binaries)} files")
