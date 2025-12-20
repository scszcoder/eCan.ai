#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Automatic Signature Update Script
Automatically calculates and updates package signatures after build
"""

import json
import hashlib
import sys
from pathlib import Path
from datetime import datetime


def calculate_sha256(file_path):
    """Calculate SHA256 hash of a file"""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        # Read in chunks to handle large files
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def auto_update_signatures(dist_dir=None, version=None):
    """
    Automatically update signatures for all packages in dist directory
    
    Args:
        dist_dir: Distribution directory path (default: project_root/dist)
        version: Version number (default: auto-detect from VERSION file)
    
    Returns:
        bool: True if successful, False otherwise
    """
    # Get project root
    script_dir = Path(__file__).parent
    project_root = script_dir.parent.parent
    
    # Determine dist directory
    if dist_dir is None:
        dist_dir = project_root / "dist"
    else:
        dist_dir = Path(dist_dir)
    
    # Determine version
    if version is None:
        version_file = project_root / "VERSION"
        if version_file.exists():
            version = version_file.read_text().strip()
        else:
            print("[ERROR] VERSION file not found, please specify version")
            return False
    
    print("=" * 60)
    print("[INFO] Automatic Signature Update")
    print("=" * 60)
    print(f"[INFO] Version: {version}")
    print(f"[INFO] Distribution directory: {dist_dir}")
    print(f"[INFO] Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    if not dist_dir.exists():
        print(f"[ERROR] Distribution directory not found: {dist_dir}")
        return False
    
    # Signature file path
    sig_file = script_dir / f"signatures_{version}.json"
    print(f"[INFO] Signature file: {sig_file}")
    print()
    
    # Package patterns to search for
    patterns = [
        "eCan-*-macos-*.pkg",
        "eCan-*-macos-*.dmg",
        "eCan-*-windows-*-Setup.exe",
        "eCan-*-windows-*.msi",
        "eCan-*-linux-*.tar.gz",
        "eCan-*-linux-*.AppImage",
    ]
    
    signatures = {}
    updated_count = 0
    
    for pattern in patterns:
        for pkg_file in dist_dir.glob(pattern):
            print(f"[INFO] Processing: {pkg_file.name}")
            
            # Calculate file size
            file_size = pkg_file.stat().st_size
            size_mb = file_size / (1024 * 1024)
            size_gb = file_size / (1024 * 1024 * 1024)
            
            if size_gb >= 1:
                size_str = f"{size_gb:.2f} GB"
            else:
                size_str = f"{size_mb:.2f} MB"
            
            print(f"   [INFO] Size: {file_size:,} bytes ({size_str})")
            
            # Calculate SHA256
            print(f"   [INFO] Calculating SHA256...")
            signature = calculate_sha256(pkg_file)
            print(f"   [OK] SHA256: {signature}")
            
            # Update signatures
            signatures[pkg_file.name] = {
                "file_size": file_size,
                "signature": signature
            }
            updated_count += 1
            print()
    
    if updated_count == 0:
        print("[WARN] No package files found in dist directory")
        print(f"   Please ensure packages are built and placed in: {dist_dir}")
        print()
        print("   Expected file patterns:")
        for pattern in patterns:
            print(f"   • {pattern}")
        return False
    
    # Save updated signatures
    with open(sig_file, 'w') as f:
        json.dump(signatures, f, indent=4)
    
    print("=" * 60)
    print(f"[OK] Updated {updated_count} package signature(s)")
    print(f"[INFO] Saved to: {sig_file}")
    print("=" * 60)
    print()
    
    # Display summary
    print("[INFO] Summary:")
    print()
    for pkg_name, info in signatures.items():
        size_mb = info['file_size'] / (1024 * 1024)
        size_gb = info['file_size'] / (1024 * 1024 * 1024)
        
        if size_gb >= 1:
            size_str = f"{size_gb:.2f} GB"
        else:
            size_str = f"{size_mb:.2f} MB"
        
        print(f"   [INFO] {pkg_name}")
        print(f"      Size: {info['file_size']:,} bytes ({size_str})")
        print(f"      SHA256: {info['signature']}")
        print()
    
    return True


def generate_appcast(version=None, base_url="http://localhost:8000"):
    """
    Generate appcast.xml from signatures
    
    Args:
        version: Version number (default: auto-detect)
        base_url: Base URL for downloads
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        from ota.server.appcast_generator import AppcastGenerator
        
        script_dir = Path(__file__).parent
        project_root = script_dir.parent.parent
        
        # Determine version
        if version is None:
            version_file = project_root / "VERSION"
            if version_file.exists():
                version = version_file.read_text().strip()
            else:
                print("[ERROR] VERSION file not found")
                return False
        
        print("=" * 60)
        print("[INFO] Generating Appcast")
        print("=" * 60)
        print(f"[INFO] Version: {version}")
        print(f"[INFO] Base URL: {base_url}")
        print()
        
        generator = AppcastGenerator(
            server_root=str(script_dir),
            signatures_dir=str(script_dir)
        )
        
        success = generator.generate_appcast(version, base_url)
        
        if success:
            print("[OK] Appcast generated successfully")
            print(f"[INFO] Location: {script_dir / 'appcast.xml'}")
        else:
            print("[ERROR] Failed to generate appcast")
        
        print("=" * 60)
        print()
        
        return success
        
    except Exception as e:
        print(f"[ERROR] Error generating appcast: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Automatically update package signatures and generate appcast"
    )
    parser.add_argument(
        "--version",
        help="Version number (default: auto-detect from VERSION file)"
    )
    parser.add_argument(
        "--dist-dir",
        help="Distribution directory (default: project_root/dist)"
    )
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="Base URL for downloads (default: http://localhost:8000)"
    )
    parser.add_argument(
        "--skip-appcast",
        action="store_true",
        help="Skip appcast generation"
    )
    
    args = parser.parse_args()
    
    # Step 1: Update signatures
    print()
    success = auto_update_signatures(
        dist_dir=args.dist_dir,
        version=args.version
    )
    
    if not success:
        print("[ERROR] Failed to update signatures")
        sys.exit(1)
    
    # Step 2: Generate appcast (unless skipped)
    if not args.skip_appcast:
        print()
        success = generate_appcast(
            version=args.version,
            base_url=args.base_url
        )
        
        if not success:
            print("[WARN] Failed to generate appcast")
            print("   Signatures were updated successfully")
    
    print()
    print("[OK] All done!")
    print()


if __name__ == "__main__":
    main()
