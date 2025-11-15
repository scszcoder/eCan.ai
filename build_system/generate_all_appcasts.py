#!/usr/bin/env python3
"""
Unified appcast generation script for all platforms and architectures.
This script replaces the inline Python code in release.yml.
"""

import os
import sys
import glob
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from build_system.generate_appcast import main as generate_appcast


def find_artifacts(platform: str, arch: str = None):
    """Find artifacts for the given platform and architecture."""
    artifacts = []
    
    if platform == 'windows':
        patterns = [
            'windows-artifacts/*.exe',
            'windows-artifacts/*.msi',
        ]
    elif platform == 'macos':
        patterns = [
            'macos-artifacts/*.pkg',
            'macos-artifacts/*.zip',
        ]
    else:
        return artifacts
    
    for pattern in patterns:
        for filepath in glob.glob(pattern):
            name = os.path.basename(filepath)
            artifacts.append({
                'name': name,
                'filepath': filepath,
            })
    
    return artifacts


def generate_appcast_for_platform(version: str, platform: str, arch: str = None):
    """Generate appcast for a specific platform and architecture."""
    s3_base_url = os.environ.get('S3_BASE_URL', '')
    
    if not s3_base_url:
        print(f"[WARN] S3_BASE_URL is empty, skipping appcast generation for {platform}/{arch or 'all'}")
        return False
    
    # Find artifacts
    artifacts = find_artifacts(platform, arch)
    if not artifacts:
        print(f"[INFO] No artifacts found for {platform}/{arch or 'all'}")
        return False
    
    # Build asset list
    assets = []
    for artifact in artifacts:
        name = artifact['name']
        filepath = artifact['filepath']
        url = f"{s3_base_url}/{platform}/{name}"
        size = os.path.getsize(filepath)
        
        assets.append({
            'name': name,
            'browser_download_url': url,
            'size': size,
            'local_path': filepath,
        })
    
    # Generate appcast
    release = {
        'tag_name': f"v{version}",
        'assets': assets,
        'body': os.environ.get('RELEASE_BODY', ''),
    }
    
    # Determine output path
    if arch:
        output_path = f'dist/appcast/appcast-{platform}-{arch}.xml'
    else:
        output_path = f'dist/appcast/appcast-{platform}.xml'
    
    # Create output directory
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # Generate appcast
    print(f"[INFO] Generating appcast for {platform}/{arch or 'all'} -> {output_path}")
    generate_appcast(release, platform_filter=platform, arch_filter=arch, output_path=output_path)
    
    return True


def main():
    """Main function."""
    version = os.environ.get('VERSION', '')
    if not version:
        print("[ERROR] VERSION environment variable not set")
        sys.exit(1)
    
    ed25519_key = os.environ.get('ED25519_PRIVATE_KEY', 'NOT_SET')
    if ed25519_key == 'NOT_SET':
        print("[WARN] ED25519_PRIVATE_KEY not set, skipping appcast generation")
        sys.exit(0)
    
    print(f"[INFO] Generating appcasts for version {version}")
    
    # Generate appcasts for all platforms and architectures
    configs = [
        ('macos', 'amd64'),
        ('macos', 'aarch64'),
        ('macos', None),  # Aggregate
        ('windows', 'amd64'),
        ('windows', None),  # Aggregate
    ]
    
    for platform, arch in configs:
        try:
            generate_appcast_for_platform(version, platform, arch)
        except Exception as e:
            print(f"[ERROR] Failed to generate appcast for {platform}/{arch or 'all'}: {e}")
            sys.exit(1)
    
    print("[INFO] All appcasts generated successfully")


if __name__ == '__main__':
    main()

