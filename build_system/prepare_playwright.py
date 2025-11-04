#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Prepare Playwright browsers for local development and testing

This script downloads Playwright browsers to third_party/ms-playwright/
for packaging into the application.

Usage:
    python build_system/prepare_playwright.py

Note:
    - In CI environments (release.yml), this is handled automatically
    - For local development, run this script before building
"""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def main():
    """Prepare Playwright browsers for packaging"""
    print("=" * 60)
    print("Playwright Browser Preparation Tool")
    print("=" * 60)
    print()
    
    try:
        # Import the utility function
        from build_system.build_utils import prepare_third_party_assets
        
        print("Preparing third-party assets (Playwright browsers)...")
        print()
        
        # Call the preparation function
        prepare_third_party_assets()
        
        print()
        print("=" * 60)
        print("Playwright browsers prepared successfully!")
        print("=" * 60)
        print()
        print("Browsers location: third_party/ms-playwright/")
        print()
        
        # Check what was downloaded
        playwright_dir = project_root / "third_party" / "ms-playwright"
        if playwright_dir.exists():
            browser_dirs = [d for d in playwright_dir.iterdir() 
                           if d.is_dir() and any(b in d.name.lower() 
                           for b in ['chromium', 'firefox', 'webkit'])]
            if browser_dirs:
                print("Downloaded browsers:")
                for browser_dir in browser_dirs:
                    print(f"   - {browser_dir.name}")
                print()
        
        print("You can now run the build:")
        print("   python build_system/unified_build.py prod")
        print()
        return 0
        
    except ImportError as e:
        print(f"Error: Failed to import build utilities: {e}")
        print()
        print("Make sure you're running this from the project root:")
        print("   python build_system/prepare_playwright.py")
        print()
        return 1
        
    except Exception as e:
        print(f"Error: Failed to prepare Playwright browsers: {e}")
        print()
        import traceback
        print("Detailed error:")
        print(traceback.format_exc())
        print()
        return 1


if __name__ == "__main__":
    sys.exit(main())

