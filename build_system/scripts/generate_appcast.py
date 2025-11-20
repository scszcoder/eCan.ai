#!/usr/bin/env python3
"""
Generate Appcast XML files from S3 artifacts (Single Bucket Design)

Usage:
    python3 build_system/scripts/generate_appcast.py --env production
    python3 build_system/scripts/generate_appcast.py --env test --channel beta

Note: This script is independent of application code and only requires boto3 and PyYAML.
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

# Project root
project_root = Path(__file__).parent.parent.parent

try:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError
except ImportError:
    print("❌ Error: boto3 is required. Install it with: pip install boto3")
    sys.exit(1)

try:
    import yaml
except ImportError:
    print("❌ Error: PyYAML is required. Install it with: pip install PyYAML")
    sys.exit(1)


def get_release_notes_from_changelog(version: str, changelog_path: Optional[Path] = None, language: str = 'en-US') -> str:
    """
    Read release notes from CHANGELOG.md for specified version (with i18n support)
    
    Args:
        version: Version number (e.g., "1.0.1")
        changelog_path: Path to CHANGELOG.md file, defaults to project root
        language: Language code (e.g., 'en-US', 'zh-CN')
    
    Returns:
        HTML formatted release notes
    """
    if changelog_path is None:
        # Prefer localized CHANGELOG for specified language
        if language != 'en-US':
            localized_changelog = project_root / f"CHANGELOG.{language}.md"
            if localized_changelog.exists():
                changelog_path = localized_changelog
            else:
                # Fallback to English version
                changelog_path = project_root / "CHANGELOG.md"
        else:
            changelog_path = project_root / "CHANGELOG.md"
    
    try:
        if not changelog_path.exists():
            return f"<h2>eCan.ai {version}</h2><p>Release notes not available.</p>"
        
        with open(changelog_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Parse Markdown and extract content for the specified version
        # Match format: ## [1.0.1] - 2025-11-21
        pattern = rf'## \[{re.escape(version)}\].*?\n(.*?)(?=\n## \[|\Z)'
        match = re.search(pattern, content, re.DOTALL)
        
        if not match:
            return f"<h2>eCan.ai {version}</h2><p>Release notes not available.</p>"
        
        notes_markdown = match.group(1).strip()
        
        # Simple Markdown to HTML conversion
        html = markdown_to_html(notes_markdown)
        
        return f"<h2>eCan.ai {version}</h2>{html}"
    
    except Exception as e:
        print(f"⚠️  Warning: Could not read release notes from CHANGELOG: {e}")
        return f"<h2>eCan.ai {version}</h2><p>Release notes not available.</p>"


def markdown_to_html(markdown_text: str) -> str:
    """
    Simple Markdown to HTML conversion
    Supports: ### headings, - lists, **bold**
    
    Args:
        markdown_text: Markdown text
    
    Returns:
        HTML text
    """
    html_lines = []
    current_list = []
    
    for line in markdown_text.split('\n'):
        line = line.strip()
        
        if not line:
            # Empty line: end current list
            if current_list:
                html_lines.append('<ul>')
                html_lines.extend(current_list)
                html_lines.append('</ul>')
                current_list = []
            continue
        
        # ### heading
        if line.startswith('### '):
            if current_list:
                html_lines.append('<ul>')
                html_lines.extend(current_list)
                html_lines.append('</ul>')
                current_list = []
            title = line[4:].strip()
            html_lines.append(f'<h3>{title}</h3>')
        
        # - list item
        elif line.startswith('- '):
            item = line[2:].strip()
            # Handle **bold**
            item = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', item)
            # Handle `code`
            item = re.sub(r'`(.*?)`', r'<code>\1</code>', item)
            current_list.append(f'  <li>{item}</li>')
        
        # Regular paragraph
        else:
            if current_list:
                html_lines.append('<ul>')
                html_lines.extend(current_list)
                html_lines.append('</ul>')
                current_list = []
            # Handle **bold**
            line = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', line)
            # Handle `code`
            line = re.sub(r'`(.*?)`', r'<code>\1</code>', line)
            html_lines.append(f'<p>{line}</p>')
    
    # Handle final list
    if current_list:
        html_lines.append('<ul>')
        html_lines.extend(current_list)
        html_lines.append('</ul>')
    
    return '\n'.join(html_lines)


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
        
        # Load configuration directly from YAML file
        config = self._load_config()
        self.bucket = config['common']['s3_bucket']
        self.region = config['common']['s3_region']
        
        # Handle S3_BASE_PATH environment variable
        # GitHub Actions may set S3_BASE_PATH="releases", but we need it to be empty
        env_base_path = os.environ.get('S3_BASE_PATH', '')
        if env_base_path == 'releases':
            # Convert "releases" to empty string for our new design
            self.base_path = ''
        else:
            # Use config file value or environment variable
            self.base_path = env_base_path or config['common'].get('s3_base_path', '')
        
        # Get environment-specific configuration
        env_config = config['environments'].get(environment, {})
        self.prefix = env_config.get('s3_prefix', environment)
        self.channel = channel or env_config.get('channel', 'stable')
        
        # Initialize S3 client
        try:
            self.s3 = boto3.client('s3', region_name=self.region)
        except NoCredentialsError:
            print("❌ Error: AWS credentials not found")
            sys.exit(1)
    
    def _load_config(self) -> dict:
        """
        Load OTA configuration from YAML file
        
        Returns:
            Configuration dictionary
        """
        config_file = project_root / 'ota' / 'config' / 'ota_config.yaml'
        
        if not config_file.exists():
            print(f"❌ Error: Configuration file not found: {config_file}")
            sys.exit(1)
        
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            return config
        except Exception as e:
            print(f"❌ Error loading configuration: {e}")
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
                
                # Build download URLs
                # Standard URL (regional endpoint)
                download_url = f"https://{self.bucket}.s3.{self.region}.amazonaws.com/{key}"
                
                # Accelerated URL (S3 Transfer Acceleration endpoint)
                # This provides faster downloads globally, especially useful for China and other regions
                accelerated_url = f"https://{self.bucket}.s3-accelerate.amazonaws.com/{key}"
                
                return {
                    'version': version,
                    'platform': platform,
                    'arch': arch,
                    'filename': filename,
                    's3_key': key,
                    'download_url': download_url,
                    'accelerated_url': accelerated_url,
                    'file_size': obj['Size'],
                    'last_modified': obj['LastModified'],
                    'sha256': sha256,
                    'signature': signature
                }
            
            return None
            
        except ClientError as e:
            print(f"  ⚠️  Failed to get package info for {version}/{platform}/{arch}: {e}")
            return None
    
    def generate_appcast_xml(self, platform: str, arch: str, max_versions: int = 10, language: str = 'en-US') -> str:
        """
        Generate appcast XML for platform and architecture (with i18n support)
        
        Args:
            platform: Platform (macos/windows)
            arch: Architecture (amd64/aarch64)
            max_versions: Maximum number of versions to include
            language: Language code (e.g., 'en-US', 'zh-CN')
        
        Returns:
            XML string
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
        ET.SubElement(channel, 'language').text = language
        
        # Add items
        for pkg in items:
            item = ET.SubElement(channel, 'item')
            
            ET.SubElement(item, 'title').text = f"Version {pkg['version']}"
            ET.SubElement(item, 'pubDate').text = pkg['last_modified'].strftime('%a, %d %b %Y %H:%M:%S +0000')
            
            # Description: Read from CHANGELOG.md (with i18n support)
            description = get_release_notes_from_changelog(pkg['version'], language=language)
            
            # Add environment-specific warnings (localized)
            if self.environment == 'development':
                description += "<div style='background-color: #fff3cd; border: 1px solid #ffc107; padding: 10px; margin-top: 10px;'>"
                if language == 'zh-CN':
                    description += "<p><strong>⚠️ 开发版本</strong></p>"
                    description += "<p>这是一个开发版本，仅供测试使用。可能包含错误和未完成的功能。</p>"
                else:
                    description += "<p><strong>⚠️ Development Build</strong></p>"
                    description += "<p>This is a development build for testing purposes only. It may contain bugs and incomplete features.</p>"
                description += "</div>"
            elif self.environment == 'test':
                description += "<div style='background-color: #d1ecf1; border: 1px solid #0c5460; padding: 10px; margin-top: 10px;'>"
                if language == 'zh-CN':
                    description += "<p><strong>ℹ️ 测试版本</strong></p>"
                    description += "<p>这是一个测试版本，如遇到问题请及时反馈。</p>"
                else:
                    description += "<p><strong>ℹ️ Beta Release</strong></p>"
                    description += "<p>This is a beta release. Please report any issues you encounter.</p>"
                description += "</div>"
            
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
            
            # Add accelerated download URL as alternate
            # Client can use this if primary URL fails or is slow
            if pkg.get('accelerated_url'):
                enclosure_attrs['sparkle:alternateUrl'] = pkg['accelerated_url']
            
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
    
    def upload_appcast(self, platform: str, arch: str, xml_content: str, language: str = 'en-US') -> bool:
        """
        Upload appcast XML to S3 (with i18n support)
        
        Args:
            platform: Platform (macos/windows)
            arch: Architecture (amd64/aarch64)
            xml_content: Appcast XML content
            language: Language code (e.g., 'en-US', 'zh-CN')
            
        Returns:
            True if successful
        """
        # Generate filename with language suffix (except for default 'en-US')
        if language == 'en-US':
            filename = f"appcast-{platform}-{arch}.xml"
        else:
            filename = f"appcast-{platform}-{arch}.{language}.xml"
        
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
        
        # Generate appcasts for each platform/arch/language combination
        combinations = [
            ('macos', 'amd64'),
            ('macos', 'aarch64'),
            ('windows', 'amd64')
        ]
        
        # Supported languages
        languages = ['en-US', 'zh-CN']
        
        for platform, arch in combinations:
            for language in languages:
                total_count += 1
                xml_content = self.generate_appcast_xml(platform, arch, language=language)
                
                if xml_content:
                    if self.upload_appcast(platform, arch, xml_content, language=language):
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
