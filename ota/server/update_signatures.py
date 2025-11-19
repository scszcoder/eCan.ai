#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Update signature file with actual package information
Automatically calculates file size and SHA256 signature for packages
"""

import json
import hashlib
from pathlib import Path


def calculate_sha256(file_path):
    """Calculate SHA256 hash of a file"""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        # Read in chunks to handle large files
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def update_signatures(version="1.1.0"):
    """
    Update signatures JSON file with actual package information
    
    Args:
        version: Version number (e.g., "1.1.0")
    """
    # Get project root
    script_dir = Path(__file__).parent
    project_root = script_dir.parent.parent
    dist_dir = project_root / "dist"
    
    # Signature file path
    sig_file = script_dir / f"signatures_{version}.json"
    
    print(f"📦 Updating signatures for version {version}")
    print(f"📁 Distribution directory: {dist_dir}")
    print(f"📄 Signature file: {sig_file}")
    print()
    
    # Load existing signatures or create new
    if sig_file.exists():
        with open(sig_file, 'r') as f:
            signatures = json.load(f)
        print("✅ Loaded existing signature file")
    else:
        signatures = {}
        print("📝 Creating new signature file")
    
    # Package patterns to search for
    patterns = [
        f"eCan-*-macos-*.pkg",
        f"eCan-*-windows-*-Setup.exe",
        f"eCan-*-linux-*.tar.gz",
    ]
    
    updated_count = 0
    
    for pattern in patterns:
        for pkg_file in dist_dir.glob(pattern):
            print(f"\n🔍 Processing: {pkg_file.name}")
            
            # Calculate file size
            file_size = pkg_file.stat().st_size
            print(f"   📏 Size: {file_size:,} bytes ({file_size / (1024**3):.2f} GB)")
            
            # Calculate SHA256
            print(f"   🔐 Calculating SHA256...")
            signature = calculate_sha256(pkg_file)
            print(f"   ✅ SHA256: {signature}")
            
            # Update signatures
            signatures[pkg_file.name] = {
                "file_size": file_size,
                "signature": signature
            }
            updated_count += 1
    
    if updated_count == 0:
        print("\n⚠️  No package files found in dist directory")
        print(f"   Please ensure packages are built and placed in: {dist_dir}")
        return False
    
    # Save updated signatures
    with open(sig_file, 'w') as f:
        json.dump(signatures, f, indent=4)
    
    print(f"\n✅ Updated {updated_count} package signature(s)")
    print(f"💾 Saved to: {sig_file}")
    
    # Display summary
    print("\n📋 Summary:")
    for pkg_name, info in signatures.items():
        print(f"   • {pkg_name}")
        print(f"     Size: {info['file_size']:,} bytes")
        print(f"     SHA256: {info['signature'][:16]}...")
    
    return True


if __name__ == "__main__":
    import sys
    
    # Get version from command line or use default
    version = sys.argv[1] if len(sys.argv) > 1 else "1.1.0"
    
    success = update_signatures(version)
    sys.exit(0 if success else 1)
