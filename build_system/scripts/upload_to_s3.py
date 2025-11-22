#!/usr/bin/env python3
"""
Upload build artifacts to S3 (Single Bucket Design)

Usage:
    python3 build_system/scripts/upload_to_s3.py --version 1.0.0 --env production
    python3 build_system/scripts/upload_to_s3.py --version 1.0.0-rc.1 --env test --platform macos --arch aarch64

Note: This script is independent of application code and only requires boto3 and PyYAML.
"""

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

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


class S3Uploader:
    """Upload build artifacts to S3 with environment-based path structure"""
    
    def __init__(self, version: str, environment: str):
        """
        Initialize S3 uploader
        
        Args:
            version: Version number (e.g., '1.0.0', '1.0.0-rc.1', '1.0.0-dev-abc123')
            environment: Target environment (dev/test/staging/production)
        """
        self.version = version
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
        
        # Get environment-specific S3 prefix
        env_config = config['environments'].get(environment, {})
        self.prefix = env_config.get('s3_prefix', environment)
        
        # Initialize S3 client
        try:
            self.s3 = boto3.client('s3', region_name=self.region)
        except NoCredentialsError:
            print("[ERROR] AWS credentials not found")
            print("   Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY environment variables")
            sys.exit(1)
        
        self.dist_dir = project_root / 'dist'
        self.uploaded_files = []
    
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
    
    def calculate_sha256(self, file_path: Path) -> str:
        """Calculate SHA256 hash of a file"""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    
    def upload_file(self, local_path: Path, s3_key: str, content_type: str = 'application/octet-stream') -> bool:
        """
        Upload a file to S3
        
        Args:
            local_path: Local file path
            s3_key: S3 object key
            content_type: MIME type
            
        Returns:
            True if successful, False otherwise
        """
        try:
            print(f"  Uploading {local_path.name} → s3://{self.bucket}/{s3_key}")
            
            self.s3.upload_file(
                str(local_path),
                self.bucket,
                s3_key,
                ExtraArgs={
                    'ContentType': content_type,
                    'CacheControl': 'max-age=3600'  # 1 hour cache
                }
            )
            
            self.uploaded_files.append({
                'local_path': str(local_path),
                's3_key': s3_key,
                's3_url': f"https://{self.bucket}.s3.{self.region}.amazonaws.com/{s3_key}",
                'size': local_path.stat().st_size
            })
            
            return True
            
        except ClientError as e:
            print(f"  [ERROR] Failed to upload {local_path.name}: {e}")
            return False
    
    def upload_windows_artifacts(self, platform_filter: Optional[str] = None) -> int:
        """
        Upload Windows installers
        
        Args:
            platform_filter: If set, only upload this platform
            
        Returns:
            Number of files uploaded
        """
        if platform_filter and platform_filter != 'windows':
            return 0
        
        print("\n[INFO] Uploading Windows artifacts...")
        count = 0
        
        # Find Windows installers
        patterns = ['*-windows-*.exe', '*-windows-*.msi']
        for pattern in patterns:
            for pkg in self.dist_dir.glob(pattern):
                # Determine architecture from filename
                arch = 'amd64'  # Windows currently only supports amd64
                
                # Build S3 key: {base_path}/{prefix}/releases/v{version}/windows/{arch}/{filename}
                if self.base_path:
                    s3_key = f"{self.base_path}/{self.prefix}/releases/v{self.version}/windows/{arch}/{pkg.name}"
                else:
                    s3_key = f"{self.prefix}/releases/v{self.version}/windows/{arch}/{pkg.name}"
                
                if self.upload_file(pkg, s3_key):
                    count += 1
                    
                    # Upload Ed25519 signature (.sig) if exists
                    sig_file = pkg.with_suffix(pkg.suffix + '.sig')
                    if sig_file.exists():
                        sig_key = f"{s3_key}.sig"
                        if self.upload_file(sig_file, sig_key, 'text/plain'):
                            print(f"  [OK] Uploaded signature: {sig_file.name}")
                    
                    # Upload SHA256 checksum
                    sha256 = self.calculate_sha256(pkg)
                    sha256_key = f"{s3_key}.sha256"
                    
                    try:
                        self.s3.put_object(
                            Bucket=self.bucket,
                            Key=sha256_key,
                            Body=sha256,
                            ContentType='text/plain'
                        )
                        print(f"  [OK] SHA256: {sha256}")
                    except ClientError as e:
                        print(f"  [WARN] Failed to upload SHA256: {e}")
        
        return count
    
    def upload_macos_artifacts(self, platform_filter: Optional[str] = None, arch_filter: Optional[str] = None) -> int:
        """
        Upload macOS installers
        
        Args:
            platform_filter: If set, only upload this platform
            arch_filter: If set, only upload this architecture
            
        Returns:
            Number of files uploaded
        """
        if platform_filter and platform_filter != 'macos':
            return 0
        
        print("\n[INFO] Uploading macOS artifacts...")
        count = 0
        
        # Find macOS installers
        for pkg in self.dist_dir.glob('*-macos-*.pkg'):
            # Determine architecture from filename
            if 'aarch64' in pkg.name or 'arm64' in pkg.name:
                arch = 'aarch64'
            else:
                arch = 'amd64'
            
            # Skip if arch filter is set and doesn't match
            if arch_filter and arch != arch_filter:
                continue
            
            # Build S3 key: {base_path}/{prefix}/releases/v{version}/macos/{arch}/{filename}
            if self.base_path:
                s3_key = f"{self.base_path}/{self.prefix}/releases/v{self.version}/macos/{arch}/{pkg.name}"
            else:
                s3_key = f"{self.prefix}/releases/v{self.version}/macos/{arch}/{pkg.name}"
            
            if self.upload_file(pkg, s3_key):
                count += 1
                
                # Upload Ed25519 signature (.sig) if exists
                sig_file = pkg.with_suffix(pkg.suffix + '.sig')
                if sig_file.exists():
                    sig_key = f"{s3_key}.sig"
                    if self.upload_file(sig_file, sig_key, 'text/plain'):
                        print(f"  [OK] Uploaded signature: {sig_file.name}")
                
                # Upload SHA256 checksum
                sha256 = self.calculate_sha256(pkg)
                sha256_key = f"{s3_key}.sha256"
                
                try:
                    self.s3.put_object(
                        Bucket=self.bucket,
                        Key=sha256_key,
                        Body=sha256,
                        ContentType='text/plain'
                    )
                    print(f"  [OK] SHA256: {sha256}")
                except ClientError as e:
                    print(f"  [WARN] Failed to upload SHA256: {e}")
        
        return count
    
    def generate_metadata(self) -> Dict:
        """Generate version metadata"""
        return {
            'version': self.version,
            'environment': self.environment,
            'build_date': datetime.now().isoformat(),
            'files': self.uploaded_files,
            's3_bucket': self.bucket,
            's3_prefix': self.prefix,
            'total_files': len(self.uploaded_files),
            'total_size': sum(f['size'] for f in self.uploaded_files)
        }
    
    def upload_metadata(self) -> bool:
        """Upload version metadata to S3"""
        print("\n[INFO] Uploading metadata...")
        
        metadata = self.generate_metadata()
        if self.base_path:
            metadata_key = f"{self.base_path}/{self.prefix}/releases/v{self.version}/metadata/version.json"
        else:
            metadata_key = f"{self.prefix}/releases/v{self.version}/metadata/version.json"
        
        try:
            self.s3.put_object(
                Bucket=self.bucket,
                Key=metadata_key,
                Body=json.dumps(metadata, indent=2),
                ContentType='application/json'
            )
            print(f"  [OK] Metadata: s3://{self.bucket}/{metadata_key}")
            return True
        except ClientError as e:
            print(f"  [ERROR] Failed to upload metadata: {e}")
            return False
    
    def update_latest_pointer(self) -> bool:
        """Update 'latest' pointer to current version"""
        print("\n[INFO] Updating latest pointer...")
        
        latest_metadata = {
            'version': self.version,
            'updated_at': datetime.now().isoformat(),
            'environment': self.environment
        }
        
        if self.base_path:
            latest_key = f"{self.base_path}/{self.prefix}/releases/latest/version.json"
        else:
            latest_key = f"{self.prefix}/releases/latest/version.json"
        
        try:
            self.s3.put_object(
                Bucket=self.bucket,
                Key=latest_key,
                Body=json.dumps(latest_metadata, indent=2),
                ContentType='application/json'
            )
            print(f"  [OK] Latest: s3://{self.bucket}/{latest_key}")
            return True
        except ClientError as e:
            print(f"  [ERROR] Failed to update latest pointer: {e}")
            return False
    
    def verify_s3_access(self) -> bool:
        """Verify S3 bucket access"""
        try:
            self.s3.head_bucket(Bucket=self.bucket)
            return True
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '404':
                print(f"[ERROR] Bucket '{self.bucket}' does not exist")
            elif error_code == '403':
                print(f"[ERROR] Access denied to bucket '{self.bucket}'")
            else:
                print(f"[ERROR] {e}")
            return False
    
    def run(self, platform_filter: Optional[str] = None, arch_filter: Optional[str] = None) -> bool:
        """
        Run the upload process
        
        Args:
            platform_filter: Only upload this platform (macos/windows)
            arch_filter: Only upload this architecture (amd64/aarch64)
            
        Returns:
            True if successful, False otherwise
        """
        print("=" * 60)
        print("[INFO] S3 Upload - Single Bucket Design")
        print("=" * 60)
        print(f"Version:     {self.version}")
        print(f"Environment: {self.environment}")
        print(f"S3 Bucket:   {self.bucket}")
        print(f"S3 Region:   {self.region}")
        print(f"S3 Prefix:   {self.prefix}")
        print(f"Dist Dir:    {self.dist_dir}")
        
        if platform_filter:
            print(f"Platform:    {platform_filter}")
        if arch_filter:
            print(f"Arch:        {arch_filter}")
        
        print("=" * 60)
        
        # Verify dist directory exists
        if not self.dist_dir.exists():
            print(f"[ERROR] Dist directory not found: {self.dist_dir}")
            return False
        
        # Verify S3 access
        print("\n[INFO] Verifying S3 access...")
        if not self.verify_s3_access():
            return False
        print("  [OK] S3 access verified")
        
        # Upload artifacts
        windows_count = self.upload_windows_artifacts(platform_filter)
        macos_count = self.upload_macos_artifacts(platform_filter, arch_filter)
        
        total_count = windows_count + macos_count
        
        if total_count == 0:
            print("\n[WARN] No artifacts found to upload")
            return False
        
        # Upload metadata
        if not self.upload_metadata():
            return False
        
        # Update latest pointer (only for stable releases)
        if self.environment in ['staging', 'production'] and '-' not in self.version:
            self.update_latest_pointer()
        
        # Summary
        print("\n" + "=" * 60)
        print("[OK] Upload Complete!")
        print("=" * 60)
        print(f"Total files uploaded: {total_count}")
        print(f"Total size: {sum(f['size'] for f in self.uploaded_files) / (1024*1024):.2f} MB")
        print("\nUploaded files:")
        for f in self.uploaded_files:
            print(f"  • {f['s3_url']}")
        print("=" * 60)
        
        return True


def main():
    parser = argparse.ArgumentParser(
        description='Upload build artifacts to S3 (Single Bucket Design)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Upload all artifacts for production
  python3 ota/scripts/upload_to_s3.py --version 1.0.0 --env production
  
  # Upload only macOS artifacts for testing
  python3 ota/scripts/upload_to_s3.py --version 1.0.0-rc.1 --env test --platform macos
  
  # Upload only macOS aarch64 for development
  python3 ota/scripts/upload_to_s3.py --version 1.0.0-dev-abc123 --env dev --platform macos --arch aarch64
        """
    )
    
    parser.add_argument('--version', required=True, help='Version number (e.g., 1.0.0, 1.0.0-rc.1)')
    parser.add_argument('--env', required=True, choices=['dev', 'development', 'test', 'staging', 'production', 'simulation'],
                       help='Target environment')
    parser.add_argument('--platform', choices=['macos', 'windows'],
                       help='Only upload this platform (optional)')
    parser.add_argument('--arch', choices=['amd64', 'aarch64'],
                       help='Only upload this architecture (optional)')
    
    args = parser.parse_args()
    
    # Create uploader and run
    uploader = S3Uploader(args.version, args.env)
    success = uploader.run(args.platform, args.arch)
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
