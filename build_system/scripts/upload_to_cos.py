#!/usr/bin/env python3
"""
Upload build artifacts to Tencent Cloud COS (CN app OTA)

Usage:
    python3 build_system/scripts/upload_to_cos.py --version 1.0.0 --env production --app cn

Note: This script uses Tencent Cloud COS S3-compatible API.
      Requires: pip install cos-python-sdk-v5 PyYAML
"""

import argparse
import hashlib
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import TYPE_CHECKING, Optional

# Project root
project_root = Path(__file__).parent.parent.parent
# Make repo-root packages importable when this script is invoked directly
# (e.g. `python3 build_system/scripts/upload_to_cos.py`); running it as a
# file puts the script directory on sys.path[0] instead of the repo root,
# which breaks `from utils.app_config_loader import ...` and similar imports.
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

if TYPE_CHECKING:
    from qcloud_cos import CosConfig, CosS3Client
    from qcloud_cos.cos_exception import CosServiceError

try:
    from qcloud_cos import CosConfig, CosS3Client
    from qcloud_cos.cos_exception import CosServiceError
except ImportError:
    print("[ERROR] cos-python-sdk-v5 is required. Install with: pip install cos-python-sdk-v5")
    sys.exit(1)

try:
    import yaml
except ImportError:
    print("[ERROR] PyYAML is required. Install with: pip install PyYAML")
    sys.exit(1)


class COSUploader:
    """Upload build artifacts to Tencent Cloud COS with per-app path structure"""

    def __init__(self, version: str, environment: str, app_id: str = 'cn'):
        self.version = version
        self.environment = environment
        self.app_id = app_id

        # Source app display info from apps/{app_id}/config/app_manifest.json
        # via utils.app_config_loader (single source of truth). The loader
        # resolves the manifest and returns safe defaults — no try/except
        # is needed here.
        from utils.app_config_loader import AppConfigLoader
        _loader = AppConfigLoader(app_id)
        self.app_name = _loader.app_short_name or _loader.app_name
        self.app_prefix = self.app_name

        self.release_dir = f"v{version}"
        self.dist_dir = project_root / 'dist'
        self.uploaded_files = []

        secret_id = os.environ.get('ECAN_TENCENT_SECRET_ID', '')
        secret_key = os.environ.get('ECAN_TENCENT_SECRET_KEY', '')

        if not secret_id or not secret_key:
            print("[ERROR] ECAN_TENCENT_SECRET_ID and ECAN_TENCENT_SECRET_KEY must be set")
            sys.exit(1)

        config_data = self._load_config()
        self.bucket = config_data['common']['cos_bucket']
        self.region = config_data['common']['cos_region']

        cos_region_map = {
            'ap-beijing': 'ap-beijing-1',
            'ap-shanghai': 'ap-shanghai',
            'ap-nanjing': 'ap-nanjing-1',
        }
        cos_region = cos_region_map.get(self.region, self.region)

        cos_config = CosConfig(
            Region=cos_region,
            SecretId=secret_id,
            SecretKey=secret_key,
            Timeout=120,  # per-request timeout (s); the 30s default was too tight for large multipart parts over GHA -> ap-shanghai
        )
        self.client = CosS3Client(cos_config, retry=5)

        env_config = config_data['environments'].get(environment, {})
        self.prefix = env_config.get('cos_prefix', environment)

    def _load_config(self) -> dict:
        config_file = project_root / 'ota' / 'config' / 'ota_config.yaml'
        if not config_file.exists():
            print(f"[ERROR] Configuration file not found: {config_file}")
            sys.exit(1)
        with open(config_file, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

    def calculate_sha256(self, file_path: Path) -> str:
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def _get_upload_id(self, cos_key: str) -> Optional[str]:
        """Get the active multipart upload ID for this key, if any.

        Returns the most recent in-progress multipart upload for ``cos_key`` so
        the caller can abort it before retrying. Uses ``list_multipart_uploads``
        (key-level listing), not ``list_parts`` which requires an UploadId we
        don't have yet.
        """
        try:
            response = self.client.list_multipart_uploads(
                Bucket=self.bucket,
                Prefix=cos_key,
            )
            for upload in response.get('Upload', []) or []:
                if upload.get('Key') == cos_key:
                    return upload.get('UploadId')
        except Exception as e:
            print(f"  [DEBUG] list_multipart_uploads failed for {cos_key}: {e}")
        return None

    def _abort_multipart_upload(self, cos_key: str) -> bool:
        """Abort incomplete multipart upload to allow clean retry."""
        try:
            upload_id = self._get_upload_id(cos_key)
            if upload_id:
                self.client.abort_multipart_upload(
                    Bucket=self.bucket,
                    Key=cos_key,
                    UploadId=upload_id,
                )
                print(f"  [DEBUG] Aborted incomplete upload for {cos_key}")
                return True
        except Exception as e:
            print(f"  [DEBUG] Could not abort multipart upload: {e}")
        return False

    def upload_file(self, local_path: Path, cos_key: str, content_type: str = 'application/octet-stream', max_retries: int = 5) -> bool:
        """Upload a file to COS with retry logic for large files.

        For files > 500MB, use 20MB parts and 5 threads so each part tolerates
        runner-to-COS network jitter. Per-request timeout and SDK retry are
        configured once on ``CosConfig`` / ``CosS3Client`` in ``__init__``.
        Uses exponential backoff for retries and aborts incomplete multipart
        uploads before retry.
        """
        import time

        file_size_mb = local_path.stat().st_size / (1024 * 1024)

        for attempt in range(1, max_retries + 1):
            try:
                # Adjust upload parameters based on file size.
                # Large files (>500MB) get bigger parts and fewer threads so
                # each in-flight PUT survives typical GHA -> ap-shanghai
                # network blips within the per-part timeout.
                if file_size_mb > 500:
                    # Very large files: 20MB parts, 5 threads
                    part_size = 20
                    max_thread = 5
                elif file_size_mb > 100:
                    # Large files: 10MB parts, 10 threads (tested reliable up to 500MB+)
                    part_size = 10
                    max_thread = 10
                else:
                    # Normal files (<100MB): 10MB parts, 5 threads
                    part_size = 10
                    max_thread = 5

                if attempt > 1:
                    # Abort any incomplete multipart upload before retrying
                    self._abort_multipart_upload(cos_key)
                    # Exponential backoff: 10s, 20s, 40s, 80s...
                    wait_time = min(10 * (2 ** (attempt - 2)), 120)
                    print(f"  [RETRY] {local_path.name} (attempt {attempt}/{max_retries}, {file_size_mb:.0f}MB)...")
                    print(f"  [RETRY] Waiting {wait_time}s before retry...")
                    time.sleep(wait_time)

                self.client.upload_file(
                    Bucket=self.bucket,
                    Key=cos_key,
                    LocalFilePath=str(local_path),
                    PartSize=part_size,
                    MAXThread=max_thread,
                    EnableMD5=False,
                    ContentType=content_type,
                )
                print(f"  [OK] {local_path.name} -> cos://{self.bucket}/{cos_key}")
                return True
            except CosServiceError as e:
                error_code = e.get_error_code()
                error_msg = e.get_error_msg()
                if attempt < max_retries:
                    print(f"  [ERROR] {local_path.name} failed (attempt {attempt}): {error_code} - {error_msg}")
                else:
                    print(f"  [ERROR] {local_path.name} failed after {max_retries} attempts: {error_code} - {error_msg}")
                if attempt >= max_retries:
                    return False
            except Exception as e:
                if attempt < max_retries:
                    print(f"  [ERROR] {local_path.name} failed (attempt {attempt}): {type(e).__name__}: {e}")
                else:
                    print(f"  [ERROR] {local_path.name} failed after {max_retries} attempts: {type(e).__name__}: {e}")
                if attempt >= max_retries:
                    return False
        return False

    def _build_cos_key(self, *parts: str) -> str:
        return '/'.join([self.prefix, 'releases', self.release_dir] + list(parts))

    def upload_windows_artifacts(self, platform_filter: Optional[str] = None) -> int:
        if platform_filter and platform_filter not in ('all', 'windows'):
            return 0
        print(f"\n[INFO] Uploading Windows artifacts for {self.app_name}...")
        patterns = [f'{self.app_prefix}-*-windows-*.exe', f'{self.app_prefix}-*-windows-*.msi']
        count = 0
        
        # Debug: List all files in dist directory
        print(f"[DEBUG] Searching for Windows artifacts in: {self.dist_dir}")
        print(f"[DEBUG] App prefix: {self.app_prefix}")
        print(f"[DEBUG] Glob patterns: {patterns}")
        all_files = list(self.dist_dir.glob('*'))
        print(f"[DEBUG] All files in dist/: {[f.name for f in all_files]}")
        exe_files = list(self.dist_dir.glob('*.exe'))
        print(f"[DEBUG] All .exe files in dist/: {[f.name for f in exe_files]}")
        
        for pattern in patterns:
            matched = list(self.dist_dir.glob(pattern))
            print(f"[DEBUG] Pattern '{pattern}' matched: {[f.name for f in matched]}")
            for pkg in matched:
                sha256_key = self._build_cos_key('windows', 'amd64', f"{pkg.name}.sha256")
                sig_key = self._build_cos_key('windows', 'amd64', f"{pkg.name}.sig")
                cos_key = self._build_cos_key('windows', 'amd64', pkg.name)

                # Compute sha256 in the background while we upload the package.
                # For an 80MB pkg this saves ~1-2s on a fast disk and ~3-5s on
                # runner CI storage.
                with ThreadPoolExecutor(max_workers=1) as hash_pool:
                    hash_future = hash_pool.submit(self.calculate_sha256, pkg)
                    upload_success = self.upload_file(pkg, cos_key, self._content_type(pkg))
                    sha256 = hash_future.result()

                # Only count as success if upload succeeded
                if not upload_success:
                    print(f"  [WARN] Upload failed for {pkg.name}, skipping SHA256 upload")
                    continue

                sha256_path = Path(f"{pkg}.sha256")
                with open(sha256_path, 'w') as f:
                    f.write(sha256)
                self.upload_file(sha256_path, sha256_key)
                sha256_path.unlink()
                count += 1

                if sig_key:
                    sig_path = Path(f"{pkg}.sig")
                    if sig_path.exists():
                        self.upload_file(sig_path, sig_key)
        
        # Debug summary
        if count == 0:
            print(f"[WARN] No Windows artifacts found matching patterns: {patterns}")
            print(f"[WARN] Expected filename format: {self.app_prefix}-<version>-windows-<arch>-Setup.exe")
            print(f"[WARN] Example: eCan.cn-0.7.0-v0.9.95b-46224882-windows-amd64-Setup.exe")
        else:
            print(f"[INFO] Successfully uploaded {count} Windows artifact(s)")
        return count

    def upload_linux_artifacts(self, platform_filter: Optional[str] = None, arch_filter: Optional[str] = None) -> int:
        if platform_filter and platform_filter not in ('all', 'linux'):
            return 0
        print(f"\n[INFO] Uploading Linux artifacts for {self.app_name}...")
        patterns = [f'{self.app_prefix}-*.AppImage', f'{self.app_prefix}-*.deb']
        count = 0
        for pattern in patterns:
            for pkg in self.dist_dir.glob(pattern):
                sha256_key = self._build_cos_key('linux', 'amd64', f"{pkg.name}.sha256")
                sig_key = self._build_cos_key('linux', 'amd64', f"{pkg.name}.sig")
                cos_key = self._build_cos_key('linux', 'amd64', pkg.name)

                with ThreadPoolExecutor(max_workers=1) as hash_pool:
                    hash_future = hash_pool.submit(self.calculate_sha256, pkg)
                    upload_success = self.upload_file(pkg, cos_key, self._content_type(pkg))
                    sha256 = hash_future.result()

                if not upload_success:
                    print(f"  [WARN] Upload failed for {pkg.name}, skipping SHA256 upload")
                    continue

                sha256_path = Path(f"{pkg}.sha256")
                with open(sha256_path, 'w') as f:
                    f.write(sha256)
                self.upload_file(sha256_path, sha256_key)
                sha256_path.unlink()
                count += 1
        return count

    def upload_macos_artifacts(self, platform_filter: Optional[str] = None, arch_filter: Optional[str] = None) -> int:
        if platform_filter and platform_filter not in ('all', 'macos'):
            return 0
        print(f"\n[INFO] Uploading macOS artifacts for {self.app_name}...")
        patterns = [f'{self.app_prefix}-*-aarch64.pkg', f'{self.app_prefix}-*-amd64.pkg']
        count = 0
        for pattern in patterns:
            for pkg in self.dist_dir.glob(pattern):
                arch = 'aarch64' if 'aarch64' in pkg.name else 'amd64'
                sha256_key = self._build_cos_key('macos', arch, f"{pkg.name}.sha256")
                sig_key = self._build_cos_key('macos', arch, f"{pkg.name}.sig")
                cos_key = self._build_cos_key('macos', arch, pkg.name)

                with ThreadPoolExecutor(max_workers=1) as hash_pool:
                    hash_future = hash_pool.submit(self.calculate_sha256, pkg)
                    upload_success = self.upload_file(pkg, cos_key, 'application/x-apple-pkg')
                    sha256 = hash_future.result()

                if not upload_success:
                    print(f"  [WARN] Upload failed for {pkg.name}, skipping SHA256 upload")
                    continue

                sha256_path = Path(f"{pkg}.sha256")
                with open(sha256_path, 'w') as f:
                    f.write(sha256)
                self.upload_file(sha256_path, sha256_key)
                sha256_path.unlink()
                count += 1
        return count

    def _content_type(self, path: Path) -> str:
        name = path.name.lower()
        if name.endswith('.exe'):
            return 'application/x-msdownload'
        elif name.endswith('.msi'):
            return 'application/x-msi'
        elif name.endswith('.pkg'):
            return 'application/x.apple.pkg'
        elif name.endswith('.dmg'):
            return 'application/x-apple-diskimage'
        elif name.endswith('.deb'):
            return 'application/x-deb'
        elif name.endswith('.AppImage'):
            return 'application/x-isoimage'
        return 'application/octet-stream'

    def upload_all(self, platform_filter: Optional[str] = None, arch_filter: Optional[str] = None) -> bool:
        print("=" * 60)
        print(f"[INFO] COS Uploader - CN App ({self.app_name})")
        print("=" * 60)
        print(f"Environment: {self.environment}")
        print(f"Version:     {self.release_dir}")
        print(f"App:         {self.app_id} ({self.app_name})")
        print(f"Bucket:      {self.bucket}")
        print(f"Region:      {self.region}")

        # Run all three platform uploaders concurrently. Each method is
        # internally sequential (one package at a time), so we get the same
        # per-file ordering as before but the three platforms no longer wait
        # for each other. Three workers is enough — going higher won't help
        # when the local runner's upload bandwidth is the bottleneck.
        with ThreadPoolExecutor(max_workers=3, thread_name_prefix="cos-up") as pool:
            futures = {
                pool.submit(self.upload_windows_artifacts, platform_filter): "windows",
                pool.submit(self.upload_macos_artifacts, platform_filter, arch_filter): "macos",
                pool.submit(self.upload_linux_artifacts, platform_filter, arch_filter): "linux",
            }
            counts = {}
            for fut in as_completed(futures):
                platform = futures[fut]
                try:
                    counts[platform] = fut.result()
                except Exception as e:
                    print(f"[ERROR] {platform} upload crashed: {e}")
                    counts[platform] = 0

        total = sum(counts.values())
        if total == 0:
            print("\n[WARN] No artifacts found to upload")
            return False

        print(f"\n[INFO] Uploaded {total} artifact(s) "
              f"(windows={counts.get('windows', 0)}, "
              f"macos={counts.get('macos', 0)}, "
              f"linux={counts.get('linux', 0)})")
        return True


def main():
    parser = argparse.ArgumentParser(description='Upload build artifacts to Tencent Cloud COS (CN app OTA)')
    parser.add_argument('--version', required=True, help='Version string (e.g. 1.0.0)')
    parser.add_argument('--env', required=True,
                        choices=['dev', 'development', 'test', 'staging', 'production', 'simulation'],
                        help='Target environment')
    parser.add_argument('--app', default='cn', choices=['cn'],
                        help='App identifier (default: cn)')
    parser.add_argument('--platform', choices=['all', 'macos', 'windows', 'linux'],
                        default='all', help='Target platform')
    parser.add_argument('--arch', choices=['all', 'amd64', 'aarch64'],
                        default='all', help='Target architecture')

    args = parser.parse_args()
    uploader = COSUploader(args.version, args.env, app_id=args.app)
    success = uploader.upload_all(platform_filter=args.platform, arch_filter=args.arch)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
