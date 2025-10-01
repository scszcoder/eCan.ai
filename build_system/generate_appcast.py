#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Appcast Generator for GitHub Release
Generate Sparkle appcast XML file for GitHub Release
"""

import os
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
import hashlib

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def calculate_file_hash(file_path: str, algorithm: str = 'sha256') -> str:
    """Calculate file hash value"""
    hash_obj = hashlib.new(algorithm)
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            hash_obj.update(chunk)
    return hash_obj.hexdigest()


def sign_update(file_path: str) -> Optional[str]:
    """Sign update file with Ed25519 private key"""
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        import base64
        
        # Get private key from environment variable
        private_key_pem = os.environ.get('ED25519_PRIVATE_KEY')
        if not private_key_pem:
            print("Warning: ED25519_PRIVATE_KEY not set, skipping signature")
            return None
        
        # Load private key
        private_key = serialization.load_pem_private_key(
            private_key_pem.encode('utf-8'),
            password=None
        )
        
        # Read file content and sign
        with open(file_path, 'rb') as f:
            file_data = f.read()
        
        signature = private_key.sign(file_data)
        return base64.b64encode(signature).decode('utf-8')
        
    except ImportError:
        print("Warning: cryptography module not available, skipping signature")
        return None
    except Exception as e:
        print(f"Warning: Failed to sign file: {e}")
        return None


def filter_assets(assets: List[Dict], platform_filter: Optional[str] = None, 
                 arch_filter: Optional[str] = None) -> List[Dict]:
    """Filter asset list by platform and architecture
    
    Args:
        assets: List of asset dictionaries
        platform_filter: Platform to filter by ('macos', 'windows', 'linux')
        arch_filter: Architecture to filter by ('amd64', 'aarch64')
        
    Returns:
        Filtered list of assets
    """
    filtered = []
    
    for asset in assets:
        name = asset['name'].lower()
        
        # Filter by platform
        if platform_filter:
            if platform_filter == 'macos':
                if not (name.endswith('.pkg') or name.endswith('.dmg') or 'macos' in name or 'darwin' in name):
                    continue
            elif platform_filter == 'windows':
                if not (name.endswith('.exe') or name.endswith('.msi') or 'windows' in name):
                    continue
            elif platform_filter == 'linux':
                if not (name.endswith('.appimage') or 'linux' in name):
                    continue
        
        # Filter by architecture
        if arch_filter:
            if arch_filter == 'amd64':
                if not any(x in name for x in ['amd64', 'x86_64', 'x64']):
                    continue
            elif arch_filter == 'aarch64':
                if not any(x in name for x in ['aarch64', 'arm64']):
                    continue
        
        filtered.append(asset)
    
    return filtered


def detect_os_and_arch(filename: str) -> tuple:
    """Detect OS and architecture from filename"""
    name_lower = filename.lower()
    
    # Detect operating system
    if 'windows' in name_lower or name_lower.endswith('.exe') or name_lower.endswith('.msi'):
        os_type = 'windows'
    elif 'macos' in name_lower or 'darwin' in name_lower or name_lower.endswith('.pkg') or name_lower.endswith('.dmg'):
        os_type = 'macos'
    elif 'linux' in name_lower or name_lower.endswith('.appimage'):
        os_type = 'linux'
    else:
        os_type = 'unknown'
    
    # Detect architecture
    if any(x in name_lower for x in ['amd64', 'x86_64', 'x64']):
        arch = 'x86_64'
    elif any(x in name_lower for x in ['aarch64', 'arm64']):
        arch = 'arm64'
    else:
        arch = 'universal'
    
    return os_type, arch


def generate_appcast_xml(release: Dict, assets: List[Dict], output_path: str):
    """Generate Sparkle appcast XML
    
    Args:
        release: Release information dictionary
        assets: List of asset dictionaries
        output_path: Path to save the generated XML file
    """
    from xml.etree import ElementTree as ET
    
    # Create RSS root element
    rss = ET.Element('rss', {
        'version': '2.0',
        'xmlns:sparkle': 'http://www.andymatuschak.org/xml-namespaces/sparkle',
        'xmlns:dc': 'http://purl.org/dc/elements/1.1/'
    })
    
    channel = ET.SubElement(rss, 'channel')
    
    # Channel information
    ET.SubElement(channel, 'title').text = 'eCan AI Assistant'
    ET.SubElement(channel, 'link').text = 'https://github.com/scszcoder/ecbot'
    ET.SubElement(channel, 'description').text = 'eCan AI Assistant Updates'
    ET.SubElement(channel, 'language').text = 'en'
    
    # Create an item for each asset
    for asset in assets:
        item = ET.SubElement(channel, 'item')
        
        version = release['tag_name'].lstrip('v')
        os_type, arch = detect_os_and_arch(asset['name'])
        
        ET.SubElement(item, 'title').text = f"eCan {version}"
        ET.SubElement(item, 'sparkle:version').text = version
        ET.SubElement(item, 'sparkle:shortVersionString').text = version
        ET.SubElement(item, 'description').text = f"eCan AI Assistant {version} for {os_type} ({arch})"
        ET.SubElement(item, 'pubDate').text = datetime.now().strftime('%a, %d %b %Y %H:%M:%S +0000')
        ET.SubElement(item, 'link').text = asset['browser_download_url']
        
        # Create enclosure element
        enclosure_attrs = {
            'url': asset['browser_download_url'],
            'length': str(asset['size']),
            'type': 'application/octet-stream',
            'sparkle:version': version,
            'sparkle:os': os_type,
        }
        
        # Add architecture information
        if arch != 'universal':
            enclosure_attrs['sparkle:arch'] = arch
        
        # Try to add signature
        # Note: In GitHub Actions, files should be in the current directory or specified path
        asset_file_path = asset.get('local_path', asset['name'])
        if os.path.exists(asset_file_path):
            signature = sign_update(asset_file_path)
            if signature:
                enclosure_attrs['sparkle:edSignature'] = signature
                
            # Add SHA256 hash for integrity verification
            try:
                sha256_hash = calculate_file_hash(asset_file_path, 'sha256')
                enclosure_attrs['sparkle:sha256'] = sha256_hash
            except Exception as e:
                print(f"Warning: Failed to calculate hash for {asset_file_path}: {e}")
        
        ET.SubElement(item, 'enclosure', enclosure_attrs)
    
    # Format and save XML
    tree = ET.ElementTree(rss)
    ET.indent(tree, space='  ')
    
    # Ensure output directory exists
    output_dir = Path(output_path).parent
    output_dir.mkdir(parents=True, exist_ok=True)
    
    tree.write(output_path, encoding='utf-8', xml_declaration=True)
    print(f"Generated appcast: {output_path}")


def main(release: Dict, platform_filter: Optional[str] = None, 
         arch_filter: Optional[str] = None, output_path: str = 'appcast.xml'):
    """
    Main function: Generate appcast XML
    
    Args:
        release: GitHub release info dict containing tag_name and assets
        platform_filter: Platform filter ('macos', 'windows', 'linux')
        arch_filter: Architecture filter ('amd64', 'aarch64')
        output_path: Output file path
    """
    print(f"Generating appcast for release: {release.get('tag_name', 'unknown')}")
    print(f"Platform filter: {platform_filter or 'all'}")
    print(f"Arch filter: {arch_filter or 'all'}")
    
    # Get asset list
    assets = release.get('assets', [])
    if not assets:
        print("Warning: No assets found in release")
        return
    
    print(f"Total assets: {len(assets)}")
    
    # Filter assets
    filtered_assets = filter_assets(assets, platform_filter, arch_filter)
    print(f"Filtered assets: {len(filtered_assets)}")
    
    if not filtered_assets:
        print("Warning: No assets match the filters")
        return
    
    # Generate appcast XML
    generate_appcast_xml(release, filtered_assets, output_path)
    print(f"Appcast generated successfully: {output_path}")


if __name__ == '__main__':
    # Test code
    test_release = {
        'tag_name': 'v0.0.1',
        'assets': [
            {
                'name': 'eCan-0.0.1-macos-amd64.pkg',
                'browser_download_url': 'https://github.com/scszcoder/ecbot/releases/download/v0.0.1/eCan-0.0.1-macos-amd64.pkg',
                'size': 100000000
            }
        ]
    }
    
    main(test_release, platform_filter='macos', arch_filter='amd64', output_path='test_appcast.xml')
