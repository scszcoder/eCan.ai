#!/usr/bin/env python3
"""
Diagnose Windows build artifacts for CN app

Run this after the Windows build to see what files were created.
"""

import os
import sys
from pathlib import Path

def diagnose():
    project_root = Path(__file__).parent.parent.parent
    dist_dir = project_root / 'dist'

    print("=" * 60)
    print("Windows Build Artifact Diagnostics")
    print("=" * 60)
    print(f"Project root: {project_root}")
    print(f"Dist directory: {dist_dir}")
    print()

    if not dist_dir.exists():
        print("[ERROR] dist/ directory does not exist!")
        print("  -> The build may have failed or not started.")
        return False

    # List all files in dist/
    print("[INFO] Files in dist/:")
    all_files = list(dist_dir.glob('*'))
    for f in sorted(all_files):
        if f.is_dir():
            print(f"  📁 {f.name}/")
        else:
            size_mb = f.stat().st_size / (1024 * 1024)
            print(f"  📄 {f.name} ({size_mb:.1f} MB)")
    print()

    # Expected patterns for CN app
    app_prefix = "eCan.cn"
    expected_patterns = [
        f"{app_prefix}-*-windows-amd64-Setup.exe",
        f"{app_prefix}-*-windows-amd64.msi",
        f"{app_prefix}/*.exe",
    ]

    print("[INFO] Searching for Windows installers...")
    found_any = False
    for pattern in expected_patterns:
        matches = list(dist_dir.glob(pattern))
        if matches:
            print(f"  ✅ Pattern '{pattern}' matched:")
            for m in matches:
                size_mb = m.stat().st_size / (1024 * 1024)
                print(f"     - {m.name} ({size_mb:.1f} MB)")
            found_any = True
        else:
            print(f"  ❌ Pattern '{pattern}' - no matches")

    print()

    # Also check for any .exe files
    exe_files = list(dist_dir.glob('*.exe'))
    if exe_files:
        print(f"[INFO] All .exe files in dist/:")
        for f in sorted(exe_files):
            size_mb = f.stat().st_size / (1024 * 1024)
            print(f"  - {f.name} ({size_mb:.1f} MB)")

    # Check for eCan directory
    ecan_dir = dist_dir / app_prefix
    if ecan_dir.exists():
        print(f"\n[INFO] Contents of {app_prefix}/ directory:")
        for f in ecan_dir.glob('*'):
            if f.is_dir():
                print(f"  📁 {f.name}/")
            else:
                size_mb = f.stat().st_size / (1024 * 1024)
                print(f"  📄 {f.name} ({size_mb:.1f} MB)")

    print()
    if not found_any:
        print("[WARN] No Windows installer found!")
        print("  Possible causes:")
        print("  1. Windows build failed - check build logs")
        print("  2. Inno Setup not installed on the build machine")
        print("  3. Build configuration error - check app name in config")
        return False
    else:
        print("[OK] Windows installer found!")
        return True

if __name__ == "__main__":
    success = diagnose()
    sys.exit(0 if success else 1)
