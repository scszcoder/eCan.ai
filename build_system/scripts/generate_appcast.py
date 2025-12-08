#!/usr/bin/env python3
"""
Generate Appcast XML files from S3 artifacts (Single Bucket Design)

Usage:
    python3 build_system/scripts/generate_appcast.py --env production
    python3 build_system/scripts/generate_appcast.py --env test --channel beta

Note: This script is independent of application code and only requires boto3 and PyYAML.
"""

import argparse
import hashlib
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
    print("[ERROR] boto3 is required. Install it with: pip install boto3")
    sys.exit(1)

try:
    import yaml
except ImportError:
    print("[ERROR] PyYAML is required. Install it with: pip install PyYAML")
    sys.exit(1)


def get_release_notes_from_changelog(version: str, changelog_path: Optional[Path] = None, language: str = 'en-US') -> str:
    """
    Read release notes from CHANGELOG.md for specified version (with i18n support)
    
    Args:
        version: Version number (e.g., "1.0.1", "1.0.0-sim", "1.0.0-gui-v2-eefbe438")
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
        
        # Extract base version number (remove suffixes like -sim, -gui-v2-eefbe438)
        # Examples:
        #   1.0.0 → 1.0.0
        #   1.0.0-sim → 1.0.0
        #   1.0.0-gui-v2-eefbe438 → 1.0.0
        base_version_match = re.match(r'(\d+\.\d+\.\d+)', version)
        if base_version_match:
            base_version = base_version_match.group(1)
        else:
            base_version = version
        
        # Parse Markdown and extract content for the base version
        # Match format: ## [1.0.1] - 2025-11-21
        pattern = rf'## \[{re.escape(base_version)}\].*?\n(.*?)(?=\n## \[|\Z)'
        match = re.search(pattern, content, re.DOTALL)
        
        if not match:
            return f"<h2>eCan.ai {version}</h2><p>Release notes not available.</p>"
        
        notes_markdown = match.group(1).strip()
        
        # Simple Markdown to HTML conversion
        html = markdown_to_html(notes_markdown)
        
        # Display full version in title, but use base version's changelog
        return f"<h2>eCan.ai {version}</h2>{html}"
    
    except Exception as e:
        print(f"[WARN] Could not read release notes from CHANGELOG: {e}")
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
    """
    Generate Appcast XML files from S3 artifacts
    """
    
    def __init__(self, environment: str, channel: str = None, specific_version: str = None):
        """
        Initialize the appcast generator
        
        Args:
            environment: Target environment (dev, test, staging, production, simulation)
            channel: Release channel (overrides environment default)
            specific_version: Specific version to generate appcast for (e.g., '1.0.1')
                            If None, scans all versions on S3
        """
        self.environment = environment
        self.specific_version = specific_version
        
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
            print("[ERROR] AWS credentials not found")
            sys.exit(1)
    
    def _load_config(self) -> dict:
        """
        Load OTA configuration from YAML file
        
        Returns:
            Configuration dictionary
        """
        config_file = project_root / 'ota' / 'config' / 'ota_config.yaml'
        
        if not config_file.exists():
            print(f"[ERROR] Configuration file not found: {config_file}")
            sys.exit(1)
        
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            return config
        except Exception as e:
            print(f"[ERROR] Error loading configuration: {e}")
            sys.exit(1)
    
    def parse_version(self, version_str: str) -> Tuple[int, int, int, int]:
        """
        Parse version string to tuple for comparison
        
        Args:
            version_str: Version string (e.g., '1.0.0', '1.0.0-rc.1', '1.0.0-gui-v2-abc')
            
        Returns:
            Version tuple (major, minor, patch, priority)
            Priority: 1000 = standard, 900 = rc, 800 = beta, 0 = branch builds
        """
        # Extract numeric parts
        match = re.match(r'(\d+)\.(\d+)\.(\d+)', version_str)
        if not match:
            return (0, 0, 0, 0)
        
        major, minor, patch = map(int, match.groups())
        
        # Determine priority based on suffix
        remainder = version_str[match.end():]
        
        if not remainder:
            # Standard version (e.g., '1.0.0')
            priority = 1000
        elif remainder.startswith('-rc.'):
            # Release candidate (e.g., '1.0.0-rc.1')
            priority = 900
        elif remainder.startswith('-beta.'):
            # Beta version (e.g., '1.0.0-beta.1')
            priority = 800
        else:
            # Branch builds or other suffixes (e.g., '1.0.0-gui-v2-abc')
            priority = 0
        
        return (major, minor, patch, priority)
    
    def list_versions(self) -> List[str]:
        """
        List versions to include in appcast
        
        Returns:
            List of version strings
            - If specific_version is set, returns only that version
            - Otherwise, scans S3 and returns all versions sorted by version number
        """
        # If specific version is provided, use only that version
        if self.specific_version:
            version = self.specific_version.lstrip('v')
            print(f"\n[INFO] Using specific version: {version}")
            return [version]
        
        # Otherwise, scan S3 for all versions
        print(f"\n[INFO] Scanning S3 for versions in {self.environment}...")
        
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
                if version == 'latest':
                    continue
                
                # Filter simulation builds in non-simulation environments
                if self.environment != 'simulation' and '-sim' in version:
                    print(f"  [SKIP] Simulation build {version} (not allowed in {self.environment} environment)")
                    continue
                
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
            print(f"  [ERROR] Failed to list versions: {e}")
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
                    sig_data = sig_obj['Body'].read()
                    # Signature is binary, need to base64 encode for Sparkle
                    import base64
                    signature = base64.b64encode(sig_data).decode('utf-8')
                except Exception as e:
                    print(f"  [WARNING] Failed to read signature for {key}: {e}")
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
            print(f"  [WARN] Failed to get package info for {version}/{platform}/{arch}: {e}")
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
        print(f"\n[INFO] Generating appcast for {platform}-{arch}...")
        
        # Get all versions
        versions = self.list_versions()
        
        # Build appcast items
        items = []
        for version in versions[:max_versions]:
            pkg_info = self.get_package_info(version, platform, arch)
            if pkg_info:
                # Filter fake signatures in non-simulation environments
                if pkg_info.get('signature') == 'fake_ed25519_signature_for_simulation':
                    if self.environment != 'simulation':
                        print(f"  [SKIP] {version} (fake signature not allowed in {self.environment} environment)")
                        continue
                    else:
                        print(f"  [OK] Added {version} (⚠️  simulation build with fake signature)")
                else:
                    print(f"  [OK] Added {version}")
                
                items.append(pkg_info)
        
        if not items:
            print(f"  [WARN] No packages found for {platform}-{arch}")
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
                    description += "<p><strong>[WARN] 开发版本</strong></p>"
                    description += "<p>这是一个开发版本，仅供测试使用。可能包含错误和未完成的功能。</p>"
                else:
                    description += "<p><strong>[WARN] Development Build</strong></p>"
                    description += "<p>This is a development build for testing purposes only. It may contain bugs and incomplete features.</p>"
                description += "</div>"
            elif self.environment == 'test':
                description += "<div style='background-color: #d1ecf1; border: 1px solid #0c5460; padding: 10px; margin-top: 10px;'>"
                if language == 'zh-CN':
                    description += "<p><strong>[INFO] 测试版本</strong></p>"
                    description += "<p>这是一个测试版本，如遇到问题请及时反馈。</p>"
                else:
                    description += "<p><strong>[INFO] Beta Release</strong></p>"
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
        Upload appcast XML to S3 with change detection (with i18n support)
        
        This method checks if the content has changed before uploading to avoid
        unnecessary S3 API calls and uploads.
        
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
        
        # Calculate hash of new content
        new_hash = hashlib.sha256(xml_content.encode('utf-8')).hexdigest()
        
        # Check if existing appcast has the same content
        try:
            response = self.s3.get_object(Bucket=self.bucket, Key=s3_key)
            existing_content = response['Body'].read().decode('utf-8')
            existing_hash = hashlib.sha256(existing_content.encode('utf-8')).hexdigest()
            
            if new_hash == existing_hash:
                print(f"  [SKIP] {filename} - No changes detected")
                return True
            else:
                print(f"  [INFO] {filename} - Content changed, uploading...")
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                print(f"  [INFO] {filename} - New file, uploading...")
            else:
                print(f"  [WARN] Failed to check existing appcast: {e}")
        
        # Upload to S3
        try:
            self.s3.put_object(
                Bucket=self.bucket,
                Key=s3_key,
                Body=xml_content.encode('utf-8'),
                ContentType='application/rss+xml; charset=utf-8',
                CacheControl='max-age=300'  # 5 minutes cache
            )
            
            url = f"https://{self.bucket}.s3.{self.region}.amazonaws.com/{s3_key}"
            print(f"  [OK] Uploaded: {url}")
            return True
            
        except ClientError as e:
            print(f"  [ERROR] Failed to upload appcast: {e}")
            return False
    
    def generate_latest_json(self) -> bool:
        """Generate and upload latest.json with current version info
        
        This method uses incremental update strategy to avoid overwriting
        platform-specific information when builds are done separately.
        """
        print(f"\n[INFO] Generating latest.json...")
        
        versions = self.list_versions()
        if not versions:
            print("  [WARN] No versions found")
            return False
        
        latest_version = versions[0]
        
        # Determine S3 key
        if self.base_path:
            s3_key = f"{self.base_path}/{self.prefix}/latest.json"
        else:
            s3_key = f"{self.prefix}/latest.json"
        
        # Try to download existing latest.json for incremental update
        existing_data = None
        try:
            response = self.s3.get_object(Bucket=self.bucket, Key=s3_key)
            existing_data = json.loads(response['Body'].read().decode('utf-8'))
            print(f"  [INFO] Found existing latest.json, will merge platform data")
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                print(f"  [INFO] No existing latest.json found, creating new one")
            else:
                print(f"  [WARN] Failed to read existing latest.json: {e}")
        
        # Initialize or update latest_data
        if existing_data:
            latest_data = existing_data
            # Update metadata
            latest_data['updated_at'] = datetime.now().isoformat()
            # Preserve existing platforms
            if 'platforms' not in latest_data:
                latest_data['platforms'] = {}
        else:
            latest_data = {
                'version': latest_version,
                'channel': self.channel,
                'environment': self.environment,
                'updated_at': datetime.now().isoformat(),
                'platforms': {}
            }
        
        # Add or update platform-specific info (incremental)
        updated_platforms = []
        for platform in ['macos', 'windows']:
            for arch in ['amd64', 'aarch64']:
                pkg_info = self.get_package_info(latest_version, platform, arch)
                if pkg_info:
                    platform_key = f"{platform}-{arch}"
                    latest_data['platforms'][platform_key] = {
                        'version': pkg_info['version'],
                        'url': pkg_info['download_url'],
                        'accelerated_url': pkg_info.get('accelerated_url'),
                        'file_size': pkg_info['file_size'],
                        'sha256': pkg_info['sha256'],
                        'signature': pkg_info['signature']
                    }
                    updated_platforms.append(platform_key)
        
        # Update global version to the latest across all platforms
        all_platform_versions = [
            info.get('version', '0.0.0') 
            for info in latest_data['platforms'].values()
        ]
        if all_platform_versions:
            # Find the highest version among all platforms
            from packaging import version as pkg_version
            try:
                latest_data['version'] = max(all_platform_versions, key=lambda v: pkg_version.parse(v))
            except Exception:
                # Fallback to simple string comparison if packaging is not available
                latest_data['version'] = max(all_platform_versions)
        
        # Upload to S3
        try:
            self.s3.put_object(
                Bucket=self.bucket,
                Key=s3_key,
                Body=json.dumps(latest_data, indent=2, ensure_ascii=False).encode('utf-8'),
                ContentType='application/json; charset=utf-8',
                CacheControl='max-age=300'
            )
            
            url = f"https://{self.bucket}.s3.{self.region}.amazonaws.com/{s3_key}"
            print(f"  [OK] Uploaded: {url}")
            if updated_platforms:
                print(f"  [INFO] Updated platforms: {', '.join(updated_platforms)}")
            print(f"  [INFO] Total platforms in latest.json: {len(latest_data['platforms'])}")
            return True
            
        except ClientError as e:
            print(f"  [ERROR] Failed to upload latest.json: {e}")
            return False
    
    def run(self, platform_filter: str = 'all', arch_filter: str = 'all') -> bool:
        """Run the appcast generation process
        
        Args:
            platform_filter: Platform filter ('all', 'macos', 'windows')
            arch_filter: Architecture filter ('all', 'amd64', 'aarch64')
        """
        print("=" * 60)
        print("[INFO] Appcast Generator - Single Bucket Design")
        print("=" * 60)
        print(f"Environment: {self.environment}")
        print(f"Channel:     {self.channel}")
        print(f"S3 Bucket:   {self.bucket}")
        print(f"S3 Region:   {self.region}")
        print(f"S3 Prefix:   {self.prefix}")
        if platform_filter != 'all' or arch_filter != 'all':
            print(f"Filter:      platform={platform_filter}, arch={arch_filter}")
        print("=" * 60)
        
        success_count = 0
        total_count = 0
        
        # All possible platform/arch combinations
        all_combinations = [
            ('macos', 'amd64'),
            ('macos', 'aarch64'),
            ('windows', 'amd64')
        ]
        
        # Apply filters
        combinations = []
        for platform, arch in all_combinations:
            if platform_filter != 'all' and platform != platform_filter:
                continue
            if arch_filter != 'all' and arch != arch_filter:
                continue
            combinations.append((platform, arch))
        
        if not combinations:
            print("[WARN] No platform/arch combinations match the filters")
            return False
        
        # Supported languages
        languages = ['en-US', 'zh-CN']
        
        for platform, arch in combinations:
            for language in languages:
                total_count += 1
                xml_content = self.generate_appcast_xml(platform, arch, language=language)
                
                if xml_content:
                    if self.upload_appcast(platform, arch, xml_content, language=language):
                        success_count += 1
        
        # Note: latest.json generation moved to separate job
        # to avoid race conditions when multiple appcast jobs run in parallel
        # See: generate-latest-json job in release.yml
        
        # Summary
        print("\n" + "=" * 60)
        if success_count == total_count:
            print("[OK] All appcasts generated successfully!")
        else:
            print(f"[WARN] Generated {success_count}/{total_count} appcasts")
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
    
    parser.add_argument('--env', required=True, choices=['dev', 'development', 'test', 'staging', 'production', 'simulation'],
                       help='Target environment')
    parser.add_argument('--channel', choices=['dev', 'beta', 'stable', 'lts', 'simulation'],
                       help='Release channel (overrides environment default)')
    parser.add_argument('--version', 
                       help='Specific version to generate appcast for (e.g., 1.0.1). If not provided, scans all versions.')
    parser.add_argument('--platform', choices=['all', 'macos', 'windows'],
                       default='all', help='Target platform (default: all)')
    parser.add_argument('--arch', choices=['all', 'amd64', 'aarch64'],
                       default='all', help='Target architecture (default: all)')
    
    args = parser.parse_args()
    
    # Create generator and run
    generator = AppcastGenerator(args.env, args.channel, specific_version=args.version)
    success = generator.run(platform_filter=args.platform, arch_filter=args.arch)
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
