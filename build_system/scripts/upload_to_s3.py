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

    # Exit-code sentinels used by the wrapper script in
    # .github/workflows/shared-s3-upload.yml. rc=2 is a hard precondition
    # failure (missing dist, no artifacts) — the wrapper renders this as a
    # red `::error::` annotation so the failure is visible in the GitHub
    # UI rather than a buried yellow warning. rc=1 is a soft runtime
    # failure (S3 unreachable, auth) — the wrapper turns that into a
    # `::warning::` plus a GHA artifact fallback URL.
    EXIT_OK = 0
    EXIT_SOFT_FAIL = 1
    EXIT_HARD_FAIL = 2

    def __init__(self, version: str, environment: str, user_prefix: str = '',
                 dist_dir: str | None = None):
        """
        Initialize S3 uploader

        Args:
            version: Version number (e.g., '1.0.0', '1.0.0-rc.1', '1.0.0-dev-abc123')
            environment: Target environment (dev/test/staging/production)
            user_prefix: Optional per-user release prefix (lowercase). When
                non-empty, the on-S3 directory name becomes
                ``{prefix}_v{version}`` instead of the default ``v{version}``.
                See ota/docs/multi_version_picker.md for the end-to-end design.
            dist_dir: Source directory of build artifacts. Defaults to
                ``<project_root>/dist`` for the historical
                GitHub-Actions-intermediate path; build jobs that call this
                script directly (release-intl.yml direct-upload fast path)
                pass an explicit path (e.g. ``artifacts/``) to skip the
                upload-artifact → download-artifact round-trip.
        """
        self.version = version
        self.environment = environment
        # Normalize: empty string and None both mean "no prefix / universal".
        self.user_prefix = (user_prefix or '').strip().lower()
        # Pre-compute the on-S3 release directory name once so every
        # platform's upload code path agrees on it. Examples:
        #   version='1.0.0', user_prefix=''        -> 'v1.0.0'
        #   version='26.05.04.09.11', prefix='songc' -> 'songc_v26.05.04.09.11'
        self.release_dir = (
            f"{self.user_prefix}_v{self.version}"
            if self.user_prefix
            else f"v{self.version}"
        )
        
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
        
        self.dist_dir = (project_root / dist_dir) if dist_dir else project_root / 'dist'
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
    
    def upload_file(self, local_path: Path, s3_key: str, content_type: str = 'application/octet-stream', max_retries: int = 3) -> bool:
        """
        Upload a file to S3 with retry logic for large files.
        
        Args:
            local_path: Local file path
            s3_key: S3 object key
            content_type: MIME type
            max_retries: Maximum number of retry attempts
            
        Returns:
            True if successful, False otherwise
        """
        import time
        from boto3.s3.transfer import TransferConfig
        from botocore.exceptions import ClientError
        
        file_size_mb = local_path.stat().st_size / (1024 * 1024)
        
        for attempt in range(1, max_retries + 1):
            try:
                if attempt > 1:
                    print(f"  [RETRY] {local_path.name} (attempt {attempt}/{max_retries}, {file_size_mb:.0f}MB)...")
                    time.sleep(5)
                
                # Use transfer config for optimized multipart uploads
                config = TransferConfig(
                    multipart_chunksize=50 * 1024 * 1024,  # 50MB chunks for large files
                    max_concurrency=10 if file_size_mb > 100 else 5
                )
                
                print(f"  Uploading {local_path.name} → s3://{self.bucket}/{s3_key}")
                
                self.s3.upload_file(
                    str(local_path),
                    self.bucket,
                    s3_key,
                    ExtraArgs={
                        'ContentType': content_type,
                        'CacheControl': 'max-age=3600'
                    },
                    Config=config
                )
                
                self.uploaded_files.append({
                    'local_path': str(local_path),
                    's3_key': s3_key,
                    's3_url': f"https://{self.bucket}.s3.{self.region}.amazonaws.com/{s3_key}",
                    'size': local_path.stat().st_size
                })
                
                return True
                
            except ClientError as e:
                if attempt < max_retries:
                    print(f"  [ERROR] {local_path.name} failed (attempt {attempt}): {e}, retrying...")
                else:
                    print(f"  [ERROR] {local_path.name} failed after {max_retries} attempts: {e}")
                if attempt >= max_retries:
                    return False
            except Exception as e:
                if attempt < max_retries:
                    print(f"  [ERROR] {local_path.name} failed (attempt {attempt}): {e}, retrying...")
                else:
                    print(f"  [ERROR] {local_path.name} failed after {max_retries} attempts: {e}")
                if attempt >= max_retries:
                    return False
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
                
                # Build S3 key: {base_path}/{prefix}/releases/{release_dir}/windows/{arch}/{filename}
                # `release_dir` is `v{version}` for semver tags, `{user_prefix}_v{version}` for user builds.
                if self.base_path:
                    s3_key = f"{self.base_path}/{self.prefix}/releases/{self.release_dir}/windows/{arch}/{pkg.name}"
                else:
                    s3_key = f"{self.prefix}/releases/{self.release_dir}/windows/{arch}/{pkg.name}"
                
                if self.upload_file(pkg, s3_key):
                    count += 1
                    
                    # Upload Ed25519 signature (.sig) if exists
                    sig_file = pkg.with_suffix(pkg.suffix + '.sig')
                    if sig_file.exists():
                        sig_key = f"{s3_key}.sig"
                        # Signature is binary (64 bytes), not text
                        if self.upload_file(sig_file, sig_key, 'application/octet-stream'):
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
    
    def upload_linux_artifacts(self, platform_filter: Optional[str] = None, arch_filter: Optional[str] = None) -> int:
        """
        Upload Linux packages (AppImage and DEB)
        
        Args:
            platform_filter: If set, only upload this platform
            arch_filter: If set, only upload this architecture
            
        Returns:
            Number of files uploaded
        """
        if platform_filter and platform_filter != 'linux':
            return 0
        
        print("\n[INFO] Uploading Linux artifacts...")
        count = 0
        
        # Find Linux packages (AppImage and DEB)
        patterns = ['*.AppImage', '*.deb']
        for pattern in patterns:
            for pkg in self.dist_dir.glob(pattern):
                # Determine architecture from filename
                if 'aarch64' in pkg.name or 'arm64' in pkg.name:
                    arch = 'aarch64'
                else:
                    arch = 'amd64'
                
                # Skip if arch filter is set and doesn't match
                if arch_filter and arch != arch_filter:
                    continue
                
                # Build S3 key: {base_path}/{prefix}/releases/{release_dir}/linux/{arch}/{filename}
                # `release_dir` is `v{version}` for semver tags, `{user_prefix}_v{version}` for user builds.
                if self.base_path:
                    s3_key = f"{self.base_path}/{self.prefix}/releases/{self.release_dir}/linux/{arch}/{pkg.name}"
                else:
                    s3_key = f"{self.prefix}/releases/{self.release_dir}/linux/{arch}/{pkg.name}"
                
                if self.upload_file(pkg, s3_key):
                    count += 1
                    
                    # Upload Ed25519 signature (.sig) if exists
                    sig_file = pkg.with_suffix(pkg.suffix + '.sig')
                    if sig_file.exists():
                        sig_key = f"{s3_key}.sig"
                        if self.upload_file(sig_file, sig_key, 'application/octet-stream'):
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
            
            # Build S3 key: {base_path}/{prefix}/releases/{release_dir}/macos/{arch}/{filename}
            # `release_dir` is `v{version}` for semver tags, `{user_prefix}_v{version}` for user builds.
            if self.base_path:
                s3_key = f"{self.base_path}/{self.prefix}/releases/{self.release_dir}/macos/{arch}/{pkg.name}"
            else:
                s3_key = f"{self.prefix}/releases/{self.release_dir}/macos/{arch}/{pkg.name}"
            
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
            # Empty string preserves prior file shape for semver builds;
            # consumers that don't know about user prefixes ignore it.
            'user_prefix': self.user_prefix,
            'release_dir': self.release_dir,
            'environment': self.environment,
            'build_date': datetime.now().isoformat(),
            'files': self.uploaded_files,
            's3_bucket': self.bucket,
            's3_prefix': self.prefix,
            'total_files': len(self.uploaded_files),
            'total_size': sum(f['size'] for f in self.uploaded_files)
        }
    
    def upload_metadata(self) -> bool:
        """Upload version metadata to S3 with incremental update
        
        This method uses incremental update strategy to avoid overwriting
        file information when builds are done separately for different platforms.
        """
        print("\n[INFO] Uploading metadata...")
        
        # Determine S3 key (uses the same release_dir as the artifact paths above).
        if self.base_path:
            metadata_key = f"{self.base_path}/{self.prefix}/releases/{self.release_dir}/metadata/version.json"
        else:
            metadata_key = f"{self.prefix}/releases/{self.release_dir}/metadata/version.json"
        
        # Try to download existing metadata for incremental update
        existing_metadata = None
        try:
            response = self.s3.get_object(Bucket=self.bucket, Key=metadata_key)
            existing_metadata = json.loads(response['Body'].read().decode('utf-8'))
            print(f"  [INFO] Found existing metadata, will merge files")
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                print(f"  [INFO] No existing metadata found, creating new one")
            else:
                print(f"  [WARN] Failed to read existing metadata: {e}")
        
        # Generate current build metadata
        current_metadata = self.generate_metadata()
        
        # Merge logic
        if existing_metadata:
            # Merge file lists (deduplicate by s3_url)
            existing_files = existing_metadata.get('files', [])
            current_files = current_metadata['files']
            
            # Use s3_url as unique identifier
            file_map = {f['s3_url']: f for f in existing_files}
            for f in current_files:
                file_map[f['s3_url']] = f  # Update or add
            
            merged_files = list(file_map.values())
            
            # Update metadata
            metadata = existing_metadata
            metadata['files'] = merged_files
            metadata['total_files'] = len(merged_files)
            metadata['total_size'] = sum(f['size'] for f in merged_files)
            metadata['build_date'] = datetime.now().isoformat()
            
            print(f"  [INFO] Merged {len(current_files)} new files with {len(existing_files)} existing files")
        else:
            metadata = current_metadata
        
        # Upload to S3
        try:
            self.s3.put_object(
                Bucket=self.bucket,
                Key=metadata_key,
                Body=json.dumps(metadata, indent=2),
                ContentType='application/json'
            )
            print(f"  [OK] Metadata: s3://{self.bucket}/{metadata_key}")
            print(f"  [INFO] Total files in metadata: {metadata['total_files']}")
            return True
        except ClientError as e:
            print(f"  [ERROR] Failed to upload metadata: {e}")
            return False
    
    # DEPRECATED: update_latest_pointer() has been removed
    # The latest/version.json file was not used by any OTA client code.
    # All clients use latest.json (generated by generate_appcast.py) instead.
    # See docs/FILE_OVERWRITE_ISSUES_AND_FIXES.md for details.
    
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

        Raises:
            _PreconditionError: when an upload cannot proceed because of a
                hard precondition failure (missing dist directory, no
                artifacts matched). The CLI translates this to exit code 2
                so the workflow wrapper can render it as a red `::error::`
                annotation. Distinguishing hard failures from soft upload
                errors (S3 unreachable, auth expired) is what lets the
                GitHub UI flag an upstream-broken build instead of burying
                it under a yellow warning.
        """
        print("=" * 60)
        print("[INFO] S3 Upload - Single Bucket Design")
        print("=" * 60)
        print(f"Version:     {self.version}")
        if self.user_prefix:
            print(f"User Prefix: {self.user_prefix}")
        print(f"Release Dir: {self.release_dir}")
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

        # Verify dist directory exists. The wrapper downloads
        # `*-installer` artifacts into `dist/` before invoking us; if
        # we land here without that directory, every build job either
        # failed or produced no artifacts, and there is nothing to
        # upload. Surface that as a hard precondition failure
        # (cf. EXIT_HARD_FAIL) so the CI UI shows a red error rather
        # than silently logging a warning.
        if not self.dist_dir.exists():
            raise _PreconditionError(f"Dist directory not found: {self.dist_dir}")

        # Verify S3 access
        print("\n[INFO] Verifying S3 access...")
        if not self.verify_s3_access():
            return False
        print("  [OK] S3 access verified")

        # Upload artifacts
        windows_count = self.upload_windows_artifacts(platform_filter)
        macos_count = self.upload_macos_artifacts(platform_filter, arch_filter)
        linux_count = self.upload_linux_artifacts(platform_filter, arch_filter)

        total_count = windows_count + macos_count + linux_count

        if total_count == 0:
            # Builds ran but produced no installable artifacts (e.g.,
            # `package_*_prod` short-circuited, or the pre-built
            # installer / .deb / .pkg never landed in dist/). Same
            # hard-fail semantics as a missing dist directory: there's
            # nothing to upload and the upstream pipeline is broken.
            raise _PreconditionError("No artifacts found to upload")

        # Upload metadata
        if not self.upload_metadata():
            return False

        # Note: latest/version.json generation has been removed (deprecated)
        # All version information is now in latest.json (generated by generate_appcast.py)

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


class _PreconditionError(Exception):
    """Raised by S3Uploader.run() when a hard precondition fails.

    See S3Uploader.EXIT_HARD_FAIL for the contract this exception
    implements (the CLI translates it to exit code 2, which the CI
    wrapper renders as a red `::error::` annotation)."""


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
    parser.add_argument('--user-prefix', default='', dest='user_prefix',
                       help=(
                           'Optional per-user release prefix (lowercase). When set, '
                           'the on-S3 directory becomes `<prefix>_v<version>` instead '
                           'of `v<version>`. See ota/docs/multi_version_picker.md.'
                       ))
    parser.add_argument('--platform', choices=['macos', 'windows'],
                       help='Only upload this platform (optional)')
    parser.add_argument('--arch', choices=['amd64', 'aarch64'],
                       help='Only upload this architecture (optional)')
    parser.add_argument('--dist-dir', default=None,
                       help='Source directory of build artifacts '
                            '(default: <project_root>/dist). Build jobs calling this '
                            'script directly (intl direct-upload fast path) pass the '
                            'platform-specific staging directory, e.g. ``artifacts/``.')

    args = parser.parse_args()

    # Create uploader and run. Hard precondition failures (missing dist,
    # no artifacts) raise _PreconditionError → exit code 2; the GitHub
    # Actions wrapper in shared-s3-upload.yml renders rc=2 as a red
    # `::error::` annotation so the failure is visible in the UI instead
    # of being buried under a yellow warning. Soft runtime failures
    # (S3 unreachable, auth) keep the historical rc=1 → ::warning::
    # contract so transient S3 problems don't false-alarm the build.
    uploader = S3Uploader(args.version, args.env, user_prefix=args.user_prefix,
                          dist_dir=args.dist_dir)
    try:
        success = uploader.run(args.platform, args.arch)
    except _PreconditionError as e:
        print(f"[ERROR] {e}")
        sys.exit(S3Uploader.EXIT_HARD_FAIL)

    sys.exit(S3Uploader.EXIT_OK if success else S3Uploader.EXIT_SOFT_FAIL)


if __name__ == "__main__":
    main()
