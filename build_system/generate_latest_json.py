#!/usr/bin/env python3
"""
Generate latest.json for a release channel.

This script creates a channel-specific latest.json file that points to:
- The latest version in that channel
- Appcast URLs for OTA updates
- Quick download links for common platforms
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any


def generate_latest_json(version: str, base_url: str, channel: str = 'stable') -> Dict[str, Any]:
    """Generate latest.json for a channel."""
    
    print(f"=== Generating latest.json for {channel} channel ===")
    print(f"Version: {version}")
    print(f"Base URL: {base_url}")
    print()
    
    # Build latest.json structure
    latest = {
        "channel": channel,
        "latest_version": version,
        "latest_tag": f"v{version}",
        "release_date": datetime.now(timezone.utc).isoformat(),
        "metadata_url": f"{base_url}/releases/v{version}/metadata.json",
        "appcast": {
            "windows": f"{base_url}/channels/{channel}/appcast-windows.xml",
            "windows_amd64": f"{base_url}/channels/{channel}/appcast-windows-amd64.xml",
            "macos": f"{base_url}/channels/{channel}/appcast-macos.xml",
            "macos_amd64": f"{base_url}/channels/{channel}/appcast-macos-amd64.xml",
            "macos_aarch64": f"{base_url}/channels/{channel}/appcast-macos-aarch64.xml"
        },
        "quick_download": {}
    }
    
    # Add quick download links based on common file patterns
    # These are best-effort URLs that may or may not exist
    quick_downloads = {
        "windows_amd64_installer": f"{base_url}/releases/v{version}/windows/eCan-{version}-windows-amd64-Setup.exe",
        "windows_amd64_msi": f"{base_url}/releases/v{version}/windows/eCan-{version}-windows-amd64.msi",
        "macos_amd64_pkg": f"{base_url}/releases/v{version}/macos/eCan-{version}-macos-amd64.pkg",
        "macos_aarch64_pkg": f"{base_url}/releases/v{version}/macos/eCan-{version}-macos-aarch64.pkg",
        "macos_aarch64_zip": f"{base_url}/releases/v{version}/macos/eCan-{version}-macos-aarch64.zip"
    }
    
    latest["quick_download"] = quick_downloads
    
    return latest


def main():
    """Main function."""
    # Get environment variables
    version = os.environ.get('VERSION', '')
    s3_base_url = os.environ.get('S3_BASE_URL', '')
    channel = os.environ.get('CHANNEL', 'stable')
    
    if not version:
        print("Error: VERSION environment variable is required", file=sys.stderr)
        sys.exit(1)
    
    if not s3_base_url:
        print("Error: S3_BASE_URL environment variable is required", file=sys.stderr)
        sys.exit(1)
    
    # Generate latest.json
    latest = generate_latest_json(version, s3_base_url, channel)
    
    # Create output directory
    output_dir = Path('dist/channels') / channel
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Write latest.json
    output_path = output_dir / 'latest.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(latest, f, indent=2, ensure_ascii=False)
    
    print(f"✅ latest.json generated: {output_path}")
    print(f"   Channel: {channel}")
    print(f"   Version: {version}")
    print(f"   Appcast URLs: {len(latest['appcast'])} platforms")
    print(f"   Quick downloads: {len(latest['quick_download'])} links")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
