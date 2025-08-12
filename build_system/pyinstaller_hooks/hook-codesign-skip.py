# Custom hook to skip codesign for problematic files
# This prevents codesign errors on macOS

import os
import sys
from pathlib import Path

# Only apply on macOS
if sys.platform == 'darwin':
    print("[CODESIGN-SKIP] macOS detected - applying codesign exclusions")
    
    # Define files that should skip codesign
    codesign_skip_patterns = [
        # Playwright browser binaries
        '**/ms-playwright/**/chromium*/chrome-mac/Chromium.app/**',
        '**/ms-playwright/**/chromium*/chrome-mac/Chromium.app/Contents/Frameworks/**',
        '**/ms-playwright/**/chromium*/chrome-mac/Chromium.app/Contents/MacOS/**',
        '**/ms-playwright/**/chromium*/chrome-mac-arm64/Chromium.app/**',
        '**/ms-playwright/**/chromium*/chrome-mac-arm64/Chromium.app/Contents/Frameworks/**',
        '**/ms-playwright/**/chromium*/chrome-mac-arm64/Chromium.app/Contents/MacOS/**',
        
        # Other problematic files
        '**/*.framework/**',
        '**/*.app/**',
    ]
    
    # Find and mark problematic files as data (not binaries)
    datas = []
    binaries = []
    
    # Look for Playwright browsers in common locations
    browser_paths = []
    
    # Check current working directory
    current_dir = Path.cwd()
    third_party_path = current_dir / "third_party" / "ms-playwright"
    if third_party_path.exists():
        browser_paths.append(third_party_path)
        print(f"[CODESIGN-SKIP] Found browsers in: {third_party_path}")
    
    # Check environment variable
    if 'PLAYWRIGHT_BROWSERS_PATH' in os.environ:
        env_path = Path(os.environ['PLAYWRIGHT_BROWSERS_PATH'])
        if env_path.exists():
            browser_paths.append(env_path)
            print(f"[CODESIGN-SKIP] Found browsers in: {env_path}")
    
    # Check user cache directories
    user_home = Path.home()
    cache_paths = [
        user_home / ".cache" / "ms-playwright",
        user_home / "Library" / "Caches" / "ms-playwright",
    ]
    
    for cache_path in cache_paths:
        if cache_path.exists():
            browser_paths.append(cache_path)
            print(f"[CODESIGN-SKIP] Found browsers in: {cache_path}")
    
    # Process found browser paths
    for browser_path in browser_paths:
        if browser_path.exists() and browser_path.is_dir():
            print(f"[CODESIGN-SKIP] Processing browser path: {browser_path}")
            
            # Find all files that should skip codesign
            for root, dirs, files in os.walk(browser_path):
                root_path = Path(root)
                
                for file in files:
                    file_path = root_path / file
                    rel_path = file_path.relative_to(browser_path)
                    
                    # Check if this file should skip codesign
                    should_skip = False
                    for pattern in codesign_skip_patterns:
                        # Simple pattern matching (PyInstaller will handle glob patterns)
                        if any(part in str(rel_path) for part in pattern.split('/')):
                            should_skip = True
                            break
                    
                    if should_skip:
                        target_path = f"third_party/ms-playwright/{rel_path}"
                        datas.append((str(file_path), target_path))
                        print(f"[CODESIGN-SKIP] Excluded from codesign: {rel_path}")
    
    print(f"[CODESIGN-SKIP] Hook loaded successfully:")
    print(f"[CODESIGN-SKIP] - Data files (codesign excluded): {len(datas)}")
    print(f"[CODESIGN-SKIP] - Binary files: {len(binaries)}")
    
else:
    # On non-macOS platforms, no special handling needed
    datas = []
    binaries = []
    print("[CODESIGN-SKIP] Non-macOS platform - no codesign exclusions needed")
