# PyInstaller hook for Playwright
# This hook ensures Playwright browsers are properly handled during packaging

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs
import os
import sys
from pathlib import Path

# Collect Playwright Python package data
datas = collect_data_files('playwright')

# On macOS, we need to handle the browser binaries specially
if sys.platform == 'darwin':
    print("[HOOK] macOS detected - applying Playwright browser handling (no duplicates)")
    
    # Find Playwright browser installation in multiple locations
    browser_paths = []
    
    # 1. Check current working directory for third_party/ms-playwright
    current_dir = Path.cwd()
    third_party_path = current_dir / "third_party" / "ms-playwright"
    if third_party_path.exists():
        browser_paths.append(third_party_path)
        print(f"[HOOK] Found browsers in: {third_party_path}")
    
    # 2. Check environment variable
    if 'PLAYWRIGHT_BROWSERS_PATH' in os.environ:
        env_path = Path(os.environ['PLAYWRIGHT_BROWSERS_PATH'])
        if env_path.exists():
            browser_paths.append(env_path)
            print(f"[HOOK] Found browsers in: {env_path}")
    
    # 3. Check user cache directories
    user_home = Path.home()
    cache_paths = [
        user_home / ".cache" / "ms-playwright",
        user_home / "Library" / "Caches" / "ms-playwright",
        user_home / "AppData" / "Local" / "ms-playwright" if sys.platform == 'win32' else None
    ]
    
    for cache_path in cache_paths:
        if cache_path and cache_path.exists():
            browser_paths.append(cache_path)
            print(f"[HOOK] Found browsers in: {cache_path}")
    
    # Only add the entire ms-playwright directory once per found path
    normalized = set()
    for browser_path in browser_paths:
        if browser_path.exists() and browser_path.is_dir():
            key = str(browser_path.resolve())
            if key in normalized:
                continue
            normalized.add(key)
            print(f"[HOOK] Adding ms-playwright directory as data: {browser_path}")
            datas.append((str(browser_path), 'third_party/ms-playwright'))
    
    # Skip any additional per-file additions to avoid duplicates and symlink conflicts
    print("[HOOK] Skipping per-file additions (Chromium.app/executables) to prevent duplicates")

# Collect any dynamic libraries
binaries = collect_dynamic_libs('playwright')

# Hidden imports that might be needed
hiddenimports = [
    'playwright.async_api',
    'playwright.sync_api',
    'playwright.driver',
]

print(f"[HOOK] Playwright hook loaded successfully:")
print(f"[HOOK] - Data files: {len(datas)}")
print(f"[HOOK] - Binary files: {len(binaries)}")
print(f"[HOOK] - Hidden imports: {len(hiddenimports)}")
