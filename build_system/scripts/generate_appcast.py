#!/usr/bin/env python3
"""
Generate Appcast XML files from S3 artifacts (Single Bucket Design)

Usage:
    python3 build_system/scripts/generate_appcast.py --env production
    python3 build_system/scripts/generate_appcast.py --env test --channel beta
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from xml.etree import ElementTree as ET

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

try:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError
except ImportError:
    print("❌ Error: boto3 is required. Install it with: pip install boto3")
    sys.exit(1)

from ota.config.loader import ota_config


class AppcastGenerator:
    """Generate Sparkle-compatible appcast XML from S3 artifacts for self-contained OTA system"""
    
    def __init__(self, environment: str, channel: Optional[str] = None):
        """
        Initialize appcast generator
        
        Args:
            environment: Target environment (dev/test/staging/production)
            channel: Release channel (overrides environment default)
        """
        self.environment = environment
        
        # Load configuration
        ota_config.environment = environment
        self.bucket = ota_config.get_common('s3_bucket', 'ecan-releases')
        self.region = ota_config.get_common('s3_region', 'us-east-1')
        
        # Handle S3_BASE_PATH environment variable
        # GitHub Actions may set S3_BASE_PATH="releases", but we need it to be empty
        env_base_path = os.environ.get('S3_BASE_PATH', '')
        if env_base_path == 'releases':
            # Convert "releases" to empty string for our new design
            self.base_path = ''
        else:
            # Use config file value or environment variable
            self.base_path = env_base_path or ota_config.get_common('s3_base_path', '')
        
        self.prefix = ota_config.get_s3_prefix()
        self.channel = channel or ota_config.get_channel()
        
        # Initialize S3 client
        try:
            self.s3 = boto3.client('s3', region_name=self.region)
        except NoCredentialsError:
            print("❌ Error: AWS credentials not found")
            sys.exit(1)
    
    def parse_version(self, version_str: str) -> Tuple[int, int, int]:
        """
        Parse version string to tuple for comparison
        
        Args:
            version_str: Version string (e.g., '1.0.0', '1.0.0-rc.1')
            
        Returns:
            Version tuple (major, minor, patch)
        """
        # Extract numeric parts only
        match = re.match(r'(\d+)\.(\d+)\.(\d+)', version_str)
        if match:
            return tuple(map(int, match.groups()))
        return (0, 0, 0)
    
    def list_versions(self) -> List[str]:
        """
        List all versions in the environment
        
        Returns:
            List of version strings sorted by version number
        """
        print(f"\n🔍 Scanning S3 for versions in {self.environment}...")
        
        if self.base_path:
            prefix = f"{self.base_path}/{self.prefix}/releases/"
        else:
            prefix = f"{self.prefix}/releases/"
        
        try:
            response = self.s3.list_objects_v2(
                Bucket=self.bucket,
                Prefix=prefix,
                Delimiter='/'
            )
            
            versions = []
            for common_prefix in response.get('CommonPrefixes', []):
                version_path = common_prefix['Prefix']
                # Extract version from path (e.g., 'dev/releases/v1.0.0/' → '1.0.0')
                version = version_path.rstrip('/').split('/')[-1]
                if version.startswith('v'):
                    version = version[1:]
                
                # Skip 'latest' directory
                if version != 'latest':
                    versions.append(version)
            
            # Sort by version number (descending)
            versions.sort(key=self.parse_version, reverse=True)
            
            print(f"  Found {len(versions)} versions")
            for v in versions[:5]:  # Show first 5
                print(f"    • {v}")
            if len(versions) > 5:
                print(f"    ... and {len(versions) - 5} more")
            
            return versions
            
        except ClientError as e:
            print(f"  ❌ Failed to list versions: {e}")
            return []
    
    def get_package_info(self, version: str, platform: str, arch: str) -> Optional[Dict]:
        """
        Get package information from S3
        
        Args:
            version: Version number
            platform: Platform (macos/windows)
            arch: Architecture (amd64/aarch64)
            
        Returns:
            Package info dict or None if not found
        """
        # Build S3 prefix for this version/platform/arch
        if self.base_path:
            prefix = f"{self.base_path}/{self.prefix}/releases/v{version}/{platform}/{arch}/"
        else:
            prefix = f"{self.prefix}/releases/v{version}/{platform}/{arch}/"
        
        try:
            response = self.s3.list_objects_v2(
                Bucket=self.bucket,
                Prefix=prefix
            )
            
            for obj in response.get('Contents', []):
                key = obj['Key']
                filename = key.split('/')[-1]
                
                # Skip checksum files
                if filename.endswith('.sha256') or filename.endswith('.sig'):
                    continue
                
                # Check if it's an installer
                if platform == 'macos' and filename.endswith('.pkg'):
                    pass
                elif platform == 'windows' and (filename.endswith('.exe') or filename.endswith('.msi')):
                    pass
                else:
                    continue
                
                # Get SHA256 checksum
                sha256 = None
                sha256_key = f"{key}.sha256"
                try:
                    sha256_obj = self.s3.get_object(Bucket=self.bucket, Key=sha256_key)
                    sha256 = sha256_obj['Body'].read().decode('utf-8').strip()
                except:
                    pass
                
                # Get Ed25519 signature
                signature = None
                sig_key = f"{key}.sig"
                try:
                    sig_obj = self.s3.get_object(Bucket=self.bucket, Key=sig_key)
                    signature = sig_obj['Body'].read().decode('utf-8').strip()
                except:
                    pass
                
                # Build download URL
                download_url = f"https://{self.bucket}.s3.{self.region}.amazonaws.com/{key}"
                
                return {
                    'version': version,
                    'platform': platform,
                    'arch': arch,
                    'filename': filename,
                    's3_key': key,
                    'download_url': download_url,
                    'file_size': obj['Size'],
                    'last_modified': obj['LastModified'],
                    'sha256': sha256,
                    'signature': signature
                }
            
            return None
            
        except ClientError as e:
            print(f"  ⚠️  Failed to get package info for {version}/{platform}/{arch}: {e}")
            return None
    
    def generate_appcast_xml(self, platform: str, arch: str, max_versions: int = 10) -> str:
        """
        Generate appcast XML for platform and architecture
        
        Args:
            platform: Platform (macos/windows)
            arch: Architecture (amd64/aarch64)
            max_versions: Maximum number of versions to include
            
        Returns:
            Appcast XML string
        """
        print(f"\n📝 Generating appcast for {platform}-{arch}...")
        
        # Get all versions
        versions = self.list_versions()
        
        # Build appcast items
        items = []
        for version in versions[:max_versions]:
            pkg_info = self.get_package_info(version, platform, arch)
            if pkg_info:
                items.append(pkg_info)
                print(f"  ✓ Added {version}")
        
        if not items:
            print(f"  ⚠️  No packages found for {platform}-{arch}")
            return None
        
        # Create XML
        rss = ET.Element('rss', {
            'version': '2.0',
            'xmlns:sparkle': 'http://www.andymatuschak.org/xml-namespaces/sparkle',
            'xmlns:dc': 'http://purl.org/dc/elements/1.1/'
        })
        
        channel = ET.SubElement(rss, 'channel')
        
        # Channel metadata
        ET.SubElement(channel, 'title').text = f"eCan.ai Updates - {self.environment.title()}"
        
        if self.base_path:
            appcast_url = f"https://{self.bucket}.s3.{self.region}.amazonaws.com/{self.base_path}/{self.prefix}/channels/{self.channel}/appcast-{platform}-{arch}.xml"
        else:
            appcast_url = f"https://{self.bucket}.s3.{self.region}.amazonaws.com/{self.prefix}/channels/{self.channel}/appcast-{platform}-{arch}.xml"
        ET.SubElement(channel, 'link').text = appcast_url
        
        ET.SubElement(channel, 'description').text = f"Updates for eCan.ai ({platform} {arch}) - {self.channel} channel"
        ET.SubElement(channel, 'language').text = 'en'
        
        # Add items
        for pkg in items:
            item = ET.SubElement(channel, 'item')
            
            ET.SubElement(item, 'title').text = f"Version {pkg['version']}"
            ET.SubElement(item, 'pubDate').text = pkg['last_modified'].strftime('%a, %d %b %Y %H:%M:%S +0000')
            
            # Description (can be enhanced with release notes)
            description = f"<h2>eCan.ai {pkg['version']}</h2>"
            if self.environment == 'development':
                description += "<p>Development build - for testing only</p>"
            elif self.environment == 'test':
                description += "<p>Beta release - please report any issues</p>"
            
            ET.SubElement(item, 'description').text = f"<![CDATA[{description}]]>"
            
            # Enclosure (download link)
            enclosure_attrs = {
                'url': pkg['download_url'],
                'length': str(pkg['file_size']),
                'type': 'application/octet-stream',
                'sparkle:version': pkg['version'],
                'sparkle:os': platform,
            }
            
            if arch:
                enclosure_attrs['sparkle:arch'] = arch
            
            # Sparkle 2.x uses edSignature for Ed25519 signatures
            if pkg.get('signature'):
                enclosure_attrs['sparkle:edSignature'] = pkg['signature']
            
            # Legacy support or additional verification
            if pkg['sha256']:
                 # Note: Some older clients might interpret dsaSignature as DSA, but we only use Ed25519 now.
                 # We keep sha256 separate from signature.
                 pass
            
            ET.SubElement(item, 'enclosure', enclosure_attrs)
        
        # Convert to string with pretty formatting
        ET.indent(rss, space='  ')
        xml_str = ET.tostring(rss, encoding='unicode', method='xml')
        
        # Add XML declaration
        xml_str = '<?xml version="1.0" encoding="utf-8"?>\n' + xml_str
        
        return xml_str
    
    def upload_appcast(self, platform: str, arch: str, xml_content: str) -> bool:
        """
        Upload appcast XML to S3
        
        Args:
            platform: Platform (macos/windows)
            arch: Architecture (amd64/aarch64)
            xml_content: Appcast XML content
            
        Returns:
            True if successful
        """
        filename = f"appcast-{platform}-{arch}.xml"
        if self.base_path:
            s3_key = f"{self.base_path}/{self.prefix}/channels/{self.channel}/{filename}"
        else:
            s3_key = f"{self.prefix}/channels/{self.channel}/{filename}"
        
        try:
            self.s3.put_object(
                Bucket=self.bucket,
                Key=s3_key,
                Body=xml_content,
                ContentType='application/rss+xml',
                CacheControl='max-age=300'  # 5 minutes cache
            )
            
            url = f"https://{self.bucket}.s3.{self.region}.amazonaws.com/{s3_key}"
            print(f"  ✓ Uploaded: {url}")
            return True
            
        except ClientError as e:
            print(f"  ❌ Failed to upload appcast: {e}")
            return False
    
    def generate_latest_json(self) -> bool:
        """Generate and upload latest.json with current version info"""
        print(f"\n📄 Generating latest.json...")
        
        versions = self.list_versions()
        if not versions:
            print("  ⚠️  No versions found")
            return False
        
        latest_version = versions[0]
        
        latest_data = {
            'version': latest_version,
            'channel': self.channel,
            'environment': self.environment,
            'updated_at': datetime.now().isoformat(),
            'platforms': {}
        }
        
        # Add download URLs for each platform/arch
        for platform in ['macos', 'windows']:
            latest_data['platforms'][platform] = {}
            
            arches = ['amd64', 'aarch64'] if platform == 'macos' else ['amd64']
            for arch in arches:
                pkg_info = self.get_package_info(latest_version, platform, arch)
                if pkg_info:
                    latest_data['platforms'][platform][arch] = {
                        'download_url': pkg_info['download_url'],
                        'file_size': pkg_info['file_size'],
                        'sha256': pkg_info['sha256']
                    }
        
        # Upload to S3
        if self.base_path:
            s3_key = f"{self.base_path}/{self.prefix}/channels/{self.channel}/latest.json"
        else:
            s3_key = f"{self.prefix}/channels/{self.channel}/latest.json"
        
        try:
            self.s3.put_object(
                Bucket=self.bucket,
                Key=s3_key,
                Body=json.dumps(latest_data, indent=2),
                ContentType='application/json',
                CacheControl='max-age=300'
            )
            
            url = f"https://{self.bucket}.s3.{self.region}.amazonaws.com/{s3_key}"
            print(f"  ✓ Uploaded: {url}")
            return True
            
        except ClientError as e:
            print(f"  ❌ Failed to upload latest.json: {e}")
            return False
    
    def run(self) -> bool:
        """Run the appcast generation process"""
        print("=" * 60)
        print("📡 Appcast Generator - Single Bucket Design")
        print("=" * 60)
        print(f"Environment: {self.environment}")
        print(f"Channel:     {self.channel}")
        print(f"S3 Bucket:   {self.bucket}")
        print(f"S3 Region:   {self.region}")
        print(f"S3 Prefix:   {self.prefix}")
        print("=" * 60)
        
        success_count = 0
        total_count = 0
        
        # Generate appcasts for each platform/arch combination
        combinations = [
            ('macos', 'amd64'),
            ('macos', 'aarch64'),
            ('windows', 'amd64')
        ]
        
        for platform, arch in combinations:
            total_count += 1
            xml_content = self.generate_appcast_xml(platform, arch)
            
            if xml_content:
                if self.upload_appcast(platform, arch, xml_content):
                    success_count += 1
        
        # Generate latest.json
        self.generate_latest_json()
        
        # Summary
        print("\n" + "=" * 60)
        if success_count == total_count:
            print("✅ All appcasts generated successfully!")
        else:
            print(f"⚠️  Generated {success_count}/{total_count} appcasts")
        print("=" * 60)
        
        return success_count > 0


def main():
    parser = argparse.ArgumentParser(
        description='Generate Appcast XML files from S3 artifacts',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate appcasts for production
  python3 ota/scripts/generate_appcast.py --env production
  
  # Generate appcasts for test environment with beta channel
  python3 ota/scripts/generate_appcast.py --env test --channel beta
  
  # Generate appcasts for development
  python3 ota/scripts/generate_appcast.py --env dev
        """
    )
    
    parser.add_argument('--env', required=True, choices=['dev', 'test', 'staging', 'production'],
                       help='Target environment')
    parser.add_argument('--channel', choices=['dev', 'beta', 'stable', 'lts'],
                       help='Release channel (overrides environment default)')
    
    args = parser.parse_args()
    
    # Create generator and run
    generator = AppcastGenerator(args.env, args.channel)
    success = generator.run()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
