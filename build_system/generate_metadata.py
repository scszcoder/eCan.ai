#!/usr/bin/env python3
"""
Generate metadata.json for a release version.

This script creates a comprehensive metadata file containing:
- Version information
- Platform-specific download URLs
- File sizes and checksums
- Release notes link
- Minimum OS versions
"""

import os
import sys
import json
import hashlib
import glob
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, Optional


def calculate_sha256(filepath: str) -> str:
    """Calculate SHA256 checksum of a file."""
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def get_file_info(filepath: str, base_url: str, version: str, platform: str) -> Dict[str, Any]:
    """Get file information including URL, size, and checksum."""
    filename = os.path.basename(filepath)
    size = os.path.getsize(filepath)
    sha256 = calculate_sha256(filepath)
    
    # Construct S3 URL: {base_url}/releases/v{version}/{platform}/{filename}
    url = f"{base_url}/releases/v{version}/{platform}/{filename}"
    
    return {
        "url": url,
        "filename": filename,
        "size": size,
        "sha256": sha256
    }


def detect_arch_from_filename(filename: str) -> Optional[str]:
    """Detect architecture from filename."""
    filename_lower = filename.lower()
    if 'amd64' in filename_lower or 'x86_64' in filename_lower or 'x64' in filename_lower:
        return 'amd64'
    elif 'aarch64' in filename_lower or 'arm64' in filename_lower:
        return 'aarch64'
    return None


def detect_file_type(filename: str) -> str:
    """Detect file type from extension."""
    if filename.endswith('.exe'):
        return 'installer'
    elif filename.endswith('.msi'):
        return 'msi'
    elif filename.endswith('.pkg'):
        return 'pkg'
    elif filename.endswith('.zip'):
        return 'zip'
    elif filename.endswith('.dmg'):
        return 'dmg'
    return 'unknown'


def process_windows_artifacts(base_url: str, version: str) -> Dict[str, Any]:
    """Process Windows artifacts and generate metadata."""
    platforms = {}
    
    # Find all Windows artifacts
    patterns = ['windows-artifacts/*.exe', 'windows-artifacts/*.msi']
    
    for pattern in patterns:
        for filepath in glob.glob(pattern):
            if not os.path.isfile(filepath):
                continue
            
            filename = os.path.basename(filepath)
            arch = detect_arch_from_filename(filename)
            file_type = detect_file_type(filename)
            
            if not arch:
                print(f"Warning: Could not detect architecture from {filename}", file=sys.stderr)
                continue
            
            # Initialize arch dict if needed
            if arch not in platforms:
                platforms[arch] = {}
            
            # Add file info
            file_info = get_file_info(filepath, base_url, version, 'windows')
            platforms[arch][file_type] = file_info
            
            print(f"  ✓ Windows {arch} {file_type}: {filename} ({file_info['size']} bytes)")
    
    return platforms


def process_macos_artifacts(base_url: str, version: str) -> Dict[str, Any]:
    """Process macOS artifacts and generate metadata."""
    platforms = {}
    
    # Find all macOS artifacts
    patterns = ['macos-artifacts/*.pkg', 'macos-artifacts/*.zip', 'macos-artifacts/*.dmg']
    
    for pattern in patterns:
        for filepath in glob.glob(pattern):
            if not os.path.isfile(filepath):
                continue
            
            filename = os.path.basename(filepath)
            arch = detect_arch_from_filename(filename)
            file_type = detect_file_type(filename)
            
            if not arch:
                print(f"Warning: Could not detect architecture from {filename}", file=sys.stderr)
                continue
            
            # Initialize arch dict if needed
            if arch not in platforms:
                platforms[arch] = {}
            
            # Add file info
            file_info = get_file_info(filepath, base_url, version, 'macos')
            platforms[arch][file_type] = file_info
            
            print(f"  ✓ macOS {arch} {file_type}: {filename} ({file_info['size']} bytes)")
    
    return platforms


def generate_metadata(version: str, base_url: str, channel: str = 'stable', 
                      release_notes: Optional[str] = None) -> Dict[str, Any]:
    """Generate complete metadata for a release."""
    
    print(f"=== Generating metadata for version {version} ===")
    print(f"Base URL: {base_url}")
    print(f"Channel: {channel}")
    print()
    
    # Process artifacts
    print("Processing Windows artifacts...")
    windows_platforms = process_windows_artifacts(base_url, version)
    
    print("\nProcessing macOS artifacts...")
    macos_platforms = process_macos_artifacts(base_url, version)
    
    # Build metadata
    metadata = {
        "version": version,
        "tag": f"v{version}",
        "channel": channel,
        "release_date": datetime.now(timezone.utc).isoformat(),
        "platforms": {}
    }
    
    # Add Windows platforms
    if windows_platforms:
        metadata["platforms"]["windows"] = windows_platforms
    
    # Add macOS platforms
    if macos_platforms:
        metadata["platforms"]["macos"] = macos_platforms
    
    # Add release notes link if provided
    if release_notes:
        metadata["release_notes"] = release_notes
    else:
        # Default release notes URL
        metadata["release_notes"] = f"{base_url}/releases/v{version}/release-notes.md"
    
    # Add minimum OS versions
    metadata["min_os_version"] = {
        "windows": "10.0",
        "macos": "11.0"
    }
    
    return metadata


def main():
    """Main function."""
    # Get environment variables
    version = os.environ.get('VERSION', '')
    s3_base_url = os.environ.get('S3_BASE_URL', '')
    channel = os.environ.get('CHANNEL', 'stable')
    release_body = os.environ.get('RELEASE_BODY', '')
    
    if not version:
        print("Error: VERSION environment variable is required", file=sys.stderr)
        sys.exit(1)
    
    if not s3_base_url:
        print("Error: S3_BASE_URL environment variable is required", file=sys.stderr)
        sys.exit(1)
    
    # Generate metadata
    metadata = generate_metadata(version, s3_base_url, channel)
    
    # Create output directory
    output_dir = Path('dist/metadata')
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Write metadata.json
    output_path = output_dir / 'metadata.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Metadata generated: {output_path}")
    print(f"   Platforms: {', '.join(metadata['platforms'].keys())}")
    
    # Also write release-notes.md if RELEASE_BODY is provided
    if release_body:
        release_notes_path = output_dir / 'release-notes.md'
        with open(release_notes_path, 'w', encoding='utf-8') as f:
            f.write(f"# Release Notes - Version {version}\n\n")
            f.write(release_body)
        print(f"✅ Release notes generated: {release_notes_path}")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
