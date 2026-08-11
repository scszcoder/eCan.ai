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
            'ap-guangzhou': 'ap-guangzhou',
            'ap-nanjing': 'ap-nanjing-1',
        }
        cos_region = cos_region_map.get(self.region, self.region)

        cos_config = CosConfig(
            Region=cos_region,
            SecretId=secret_id,
            SecretKey=secret_key,
        )
        self.client = CosS3Client(cos_config)

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

    def upload_file(self, local_path: Path, cos_key: str, content_type: str = 'application/octet-stream') -> bool:
        try:
            with open(local_path, 'rb') as f:
                self.client.put_object(
                    Bucket=self.bucket,
                    Body=f,
                    Key=cos_key,
                    ContentType=content_type,
                )
            print(f"  [OK] {local_path.name} -> cos://{self.bucket}/{cos_key}")
            return True
        except CosServiceError as e:
            print(f"  [ERROR] {local_path.name} failed: {e.get_error_code()}")
            return False
        except Exception as e:
            print(f"  [ERROR] {local_path.name} failed: {e}")
            return False

    def _build_cos_key(self, *parts: str) -> str:
        return '/'.join([self.prefix, 'releases', self.release_dir] + list(parts))

    def upload_windows_artifacts(self, platform_filter: Optional[str] = None) -> int:
        if platform_filter and platform_filter not in ('all', 'windows'):
            return 0
        print(f"\n[INFO] Uploading Windows artifacts for {self.app_name}...")
        patterns = ['eCan.cn-*-windows-*.exe', 'eCan.cn-*-windows-*.msi']
        count = 0
        for pattern in patterns:
            for pkg in self.dist_dir.glob(pattern):
                sha256_key = self._build_cos_key('windows', 'amd64', f"{pkg.name}.sha256")
                sig_key = self._build_cos_key('windows', 'amd64', f"{pkg.name}.sig")
                cos_key = self._build_cos_key('windows', 'amd64', pkg.name)

                sha256 = self.calculate_sha256(pkg)
                with open(f"{pkg}.sha256", 'w') as f:
                    f.write(sha256)
                sha256_path = Path(f"{pkg}.sha256")

                self.upload_file(pkg, cos_key, self._content_type(pkg))
                self.upload_file(sha256_path, sha256_key)
                sha256_path.unlink()
                count += 1

                if sig_key:
                    sig_path = Path(f"{pkg}.sig")
                    if sig_path.exists():
                        self.upload_file(sig_path, sig_key)
        return count

    def upload_linux_artifacts(self, platform_filter: Optional[str] = None, arch_filter: Optional[str] = None) -> int:
        if platform_filter and platform_filter not in ('all', 'linux'):
            return 0
        print(f"\n[INFO] Uploading Linux artifacts for {self.app_name}...")
        patterns = ['eCan.cn-*.AppImage', 'eCan.cn-*.deb']
        count = 0
        for pattern in patterns:
            for pkg in self.dist_dir.glob(pattern):
                sha256 = self.calculate_sha256(pkg)
                sha256_key = self._build_cos_key('linux', 'amd64', f"{pkg.name}.sha256")
                sig_key = self._build_cos_key('linux', 'amd64', f"{pkg.name}.sig")
                cos_key = self._build_cos_key('linux', 'amd64', pkg.name)

                with open(f"{pkg}.sha256", 'w') as f:
                    f.write(sha256)
                sha256_path = Path(f"{pkg}.sha256")

                self.upload_file(pkg, cos_key, self._content_type(pkg))
                self.upload_file(sha256_path, sha256_key)
                sha256_path.unlink()
                count += 1
        return count

    def upload_macos_artifacts(self, platform_filter: Optional[str] = None, arch_filter: Optional[str] = None) -> int:
        if platform_filter and platform_filter not in ('all', 'macos'):
            return 0
        print(f"\n[INFO] Uploading macOS artifacts for {self.app_name}...")
        patterns = ['eCan.cn-*-aarch64.pkg', 'eCan.cn-*-amd64.pkg']
        count = 0
        for pattern in patterns:
            for pkg in self.dist_dir.glob(pattern):
                sha256 = self.calculate_sha256(pkg)
                arch = 'aarch64' if 'aarch64' in pkg.name else 'amd64'
                sha256_key = self._build_cos_key('macos', arch, f"{pkg.name}.sha256")
                sig_key = self._build_cos_key('macos', arch, f"{pkg.name}.sig")
                cos_key = self._build_cos_key('macos', arch, pkg.name)

                with open(f"{pkg}.sha256", 'w') as f:
                    f.write(sha256)
                sha256_path = Path(f"{pkg}.sha256")

                self.upload_file(pkg, cos_key, 'application/x-apple-pkg')
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

        windows_count = self.upload_windows_artifacts(platform_filter)
        macos_count = self.upload_macos_artifacts(platform_filter, arch_filter)
        linux_count = self.upload_linux_artifacts(platform_filter, arch_filter)

        total = windows_count + macos_count + linux_count
        if total == 0:
            print("\n[WARN] No artifacts found to upload")
            return False

        print(f"\n[INFO] Uploaded {total} artifact(s)")
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
