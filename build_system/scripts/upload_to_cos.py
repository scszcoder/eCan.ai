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
import math
import os
import signal
import sys
import threading
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
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


# ---------------------------------------------------------------------------
# Cooperative cancellation
# ---------------------------------------------------------------------------
# GitHub Actions sends SIGTERM to a step's process tree when the workflow is
# cancelled, then SIGKILL after ~30s. By default Python will raise SystemExit
# on SIGTERM, but only when the main thread is executing Python bytecode --
# while it's blocked inside a C-extension call (requests' send/recv, socket
# IO, or qcloud_cos's multipart upload), the signal queues up and the process
# appears frozen until SIGKILL.
#
# To make the cancel button responsive during a long upload we:
#   1. Install signal handlers that flip a module-level Event instead of
#      raising (so the SDK call can still unwind cleanly when its current
#      PUT finishes).
#   2. Replace any `time.sleep` with `wait_or_stopped`, which returns as
#      soon as the Event is set -- so SIGTERM wakes up the retry backoff
#      immediately.
#   3. Pass the Event into `as_completed` so the main loop stops blocking
#      on futures the moment cancellation is requested.
# ---------------------------------------------------------------------------
_stop_event = threading.Event()


def request_stop(reason: str = "") -> None:
    """Idempotently flag the upload loop to exit ASAP."""
    if not _stop_event.is_set():
        _stop_event.set()
        if reason:
            print(f"\n[STOP] Cancellation requested ({reason}); aborting upload loop...", flush=True)


def _on_sigterm(signum, frame):
    request_stop(f"signal {signum}")


def _on_sigint(signum, frame):
    request_stop(f"signal {signum}")


def install_signal_handlers() -> None:
    """Register SIGTERM/SIGINT handlers. Safe to call multiple times."""
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, _on_sigterm if sig == signal.SIGTERM else _on_sigint)
        except (ValueError, OSError):
            # signal() can fail if not called from the main thread, or on
            # platforms that don't expose the signal (e.g. Windows threads).
            pass


def wait_or_stopped(seconds: float) -> bool:
    """Sleep up to ``seconds``, returning early if cancellation was requested.

    Returns True if the wait completed normally, False if it was interrupted.
    """
    return not _stop_event.wait(seconds)


def stop_requested() -> bool:
    return _stop_event.is_set()


# ---------------------------------------------------------------------------
# Multipart chunk-size policy
# ---------------------------------------------------------------------------
# Tencent Cloud COS multipart upload limits (see
# https://www.tencentcloud.com/document/product/436/14112):
#   - PartSize: 1 MB - 5 GB per part, last part may be < 1 MB
#   - Max 10,000 parts per object
#   - Simple PUT Object caps at 5 GB; above that, multipart is mandatory
#
# The SDK's ``upload_file`` chooses PUT vs multipart based on
# ``file_size <= PartSize`` (per the docs: "对于小于等于 PartSize 的文件调用简单
# 上传"). That means a PartSize of 10 MB puts a 9 MB file into multipart and
# the resulting single part would be < 1 MB -> 400 EntityTooSmall. We
# therefore keep PartSize at 5 MB for the small branch so a 9 MB file
# splits into 2 parts of ~5 MB each, well above the 1 MB minimum.
#
# NOTE: Keep this function pure (no I/O, no SDK calls). It is called both at
# runtime by ``upload_file`` and by the unit tests in
# ``tests/unit/test_upload_to_cos_chunking.py``. Adding side effects here
# breaks the testability guarantee.
def chunk_params_for(file_size_mb: float) -> tuple[int, int]:
    """Return ``(PartSize, MAXThread)`` for an artifact of ``file_size_mb`` MB.

    Branches are tuned for the GHA -> ap-shanghai path, where small parts
    tolerate jitter better but excessive concurrency wastes runner CPU. See
    the inline comments in ``upload_file`` for the historical numbers.

    Branch semantics use ``>=`` (inclusive):
      * file_size_mb >= 500 -> very-large   (20MB parts, 10 threads)
      * file_size_mb >= 100 -> mid-large    (10MB parts, 10 threads)
      * otherwise           -> small        ( 5MB parts,  5 threads)

    The 5MB PartSize for the small branch is deliberate: the SDK routes
    files smaller than PartSize through simple PUT (no chunking), so
    anything 5MB or larger goes through multipart with every part >= 1MB
    (the COS lower bound). A 9MB file therefore becomes 2 parts of ~5MB
    each, never triggering ``400 EntityTooSmall``.
    """
    if file_size_mb >= 500:
        # Very large files: 20MB parts keep total part count well under the
        # 10,000-part COS cap even at the 5 GB simple-upload boundary
        # (5 GB / 20 MB = 250 parts). 10 threads -- matched to the mid-large
        # branch so a 600MB file uploads in ~8 minutes instead of ~15 on the
        # GHA -> ap-shanghai path (60MB / 10 threads concurrency was the
        # tuning point; below that throughput collapses on this network).
        return 20, 10
    if file_size_mb >= 100:
        # Mid-large: 10MB parts, 10 threads. Tested reliable up to 500MB+.
        return 10, 10
    # Small files (<100MB): 5MB parts, 5 threads. Files below the PartSize
    # threshold fall through to simple PUT inside the SDK, so the part-count
    # cap does not apply. 5MB is high enough to avoid <1MB EntityTooSmall
    # on a 9MB file (worst case: 2 parts of 5MB + 4MB).
    return 5, 5


class COSUploader:
    """Upload build artifacts to Tencent Cloud COS with per-app path structure"""

    # Exit-code sentinels used by the wrapper script in
    # .github/workflows/shared-cos-upload.yml. rc=2 is a hard precondition
    # failure (no dist, no artifacts matched) — the wrapper renders this as
    # a red `::error::` annotation so the failure is visible in the
    # GitHub UI rather than a buried yellow warning. rc=1 is a soft runtime
    # failure (COS unreachable, auth expired) — the wrapper turns that into
    # a `::warning::` plus a GHA artifact fallback URL.
    EXIT_OK = 0
    EXIT_SOFT_FAIL = 1
    EXIT_HARD_FAIL = 2

    def __init__(self, version: str, environment: str, app_id: str = 'cn',
                 dist_dir: str | None = None):
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
        # Source directory of build artifacts. Defaults to <project_root>/dist
        # for the historical GitHub-Actions-intermediate path; build jobs
        # that call this script directly (release-cn.yml direct-upload
        # fast path) pass an explicit path (e.g. ``artifacts/``) to skip the
        # upload-artifact → download-artifact round-trip.
        self.dist_dir = (project_root / dist_dir) if dist_dir else project_root / 'dist'
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

        # Route COS API calls through Tencent's accelerated domain whenever
        # possible. The default `cos.<region>.myqcloud.com` endpoint has
        # been observed to cap at ~0.35 MB/s from an external client
        # (GHA runners in us-east-1 hit this on the GHA -> ap-shanghai
        # path), whereas the accelerated endpoint lands on Tencent's
        # private backbone and is materially faster. Defaults are ON;
        # set ``ECAN_COS_ACCELERATE=0`` to fall back to the legacy
        # endpoint if acceleration triggers a bucket-policy or CORS
        # issue at the receiving end.
        #
        # Acceleration is scoped to this upload script on purpose:
        # runtime traffic (avatar upload, skill download, appcast
        # fetches) keeps the default regional endpoint to avoid extra
        # CDN cost and rate-limit risk.
        from utils.storage.cos_endpoints import accelerated_endpoint
        cos_endpoint = accelerated_endpoint()

        cos_config_kwargs = dict(
            Region=cos_region,
            SecretId=secret_id,
            SecretKey=secret_key,
            Timeout=120,  # per-request timeout (s); the 30s default was too tight for large multipart parts over GHA -> ap-shanghai
        )
        if cos_endpoint:
            cos_config_kwargs['Endpoint'] = cos_endpoint
        cos_config = CosConfig(**cos_config_kwargs)
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
        # 1 MiB read blocks. 4 KiB is the historical default but issues ~250x
        # more read() syscalls for a 600 MiB artifact; the SHA256 throughput
        # improvement is 2-3x on both local disks and runner CI storage.
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(1024 * 1024), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def _get_upload_id(self, cos_key: str) -> Optional[str]:
        """Get the active multipart upload ID for this key, if any.

        Returns the most recent in-progress multipart upload for ``cos_key`` so
        the caller can abort it before retrying. Uses ``list_multipart_uploads``
        (key-level listing), not ``list_parts`` which requires an UploadId we
        don't have yet.
        """
        if stop_requested():
            return None
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

        For files > 500MB, use 20MB parts and 10 threads so a 600MB
        Windows installer finishes within the 30-minute GitHub Actions
        step timeout on the GHA -> ap-shanghai path (tested with
        ``chunk_params_for`` boundaries, see
        ``tests/unit/test_upload_to_cos_chunking.py``). Per-request
        timeout and SDK retry are configured once on ``CosConfig`` /
        ``CosS3Client`` in ``__init__``. Uses exponential backoff for
        retries and aborts incomplete multipart uploads before retry.
        """
        file_size_mb = local_path.stat().st_size / (1024 * 1024)

        for attempt in range(1, max_retries + 1):
            try:
                # Centralised chunk-size policy. See chunk_params_for() for
                # the rationale and the COS limits behind each branch.
                part_size, max_thread = chunk_params_for(file_size_mb)

                if attempt > 1:
                    # Abort any incomplete multipart upload before retrying.
                    # Skip the abort round-trip if the runner already asked
                    # us to stop -- it just adds latency before SIGKILL.
                    if not stop_requested():
                        self._abort_multipart_upload(cos_key)
                    # Exponential backoff: 10s, 20s, 40s, 80s...
                    wait_time = min(10 * (2 ** (attempt - 2)), 120)
                    print(f"  [RETRY] {local_path.name} (attempt {attempt}/{max_retries}, {file_size_mb:.0f}MB)...")
                    print(f"  [RETRY] Waiting up to {wait_time}s before retry...", flush=True)
                    if not wait_or_stopped(wait_time):
                        print(f"  [STOP] Aborted retry of {local_path.name} due to cancellation", flush=True)
                        return False

                self.client.upload_file(
                    Bucket=self.bucket,
                    Key=cos_key,
                    LocalFilePath=str(local_path),
                    PartSize=part_size,
                    MAXThread=max_thread,
                    EnableMD5=False,
                    ContentType=content_type,
                )
                # Surface the chunking policy in the log so a reviewer can
                # verify at a glance that we are within the COS 10000-part
                # cap (see tests/unit/test_upload_to_cos_chunking.py).
                parts_used = max(1, math.ceil(file_size_mb / part_size))
                print(
                    f"  [OK] {local_path.name} ({file_size_mb:.0f}MB, "
                    f"{parts_used} part(s) x {part_size}MB, {max_thread} thread(s)) "
                    f"-> cos://{self.bucket}/{cos_key}"
                )
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
        if stop_requested():
            return 0
        print(f"\n[INFO] Uploading Windows artifacts for {self.app_name}...")
        # Anchor the glob on the current version. Without this,
        # self-hosted runner workspace persistence leaves behind
        # installers from previous runs (the artifact staging dir
        # is not auto-cleared between invocations), and the previous
        # `*-windows-*.exe` glob happily matched every one — which
        # then got uploaded under the current run's version prefix,
        # polluting the bucket with dead links in the appcast.
        patterns = [
            f'{self.app_prefix}-{self.version}-windows-*.exe',
            f'{self.app_prefix}-{self.version}-windows-*.msi',
        ]
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
                if stop_requested():
                    print(f"[STOP] Stopping Windows upload loop early", flush=True)
                    return count
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
        if stop_requested():
            return 0
        print(f"\n[INFO] Uploading Linux artifacts for {self.app_name}...")
        # Same version-anchor as upload_windows_artifacts — see the
        # comment there for the full rationale. Without this, stale
        # .deb / .AppImage files from previous runs get re-uploaded
        # under the current version prefix and corrupt the appcast.
        patterns = [
            f'{self.app_prefix}-{self.version}-*.AppImage',
            f'{self.app_prefix}-{self.version}-*.deb',
        ]
        count = 0
        for pattern in patterns:
            for pkg in self.dist_dir.glob(pattern):
                if stop_requested():
                    print(f"[STOP] Stopping Linux upload loop early", flush=True)
                    return count
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
        if stop_requested():
            return 0
        print(f"\n[INFO] Uploading macOS artifacts for {self.app_name}...")
        # Same version-anchor as upload_windows_artifacts — see the
        # comment there for the full rationale.
        patterns = [
            f'{self.app_prefix}-{self.version}-*-aarch64.pkg',
            f'{self.app_prefix}-{self.version}-*-amd64.pkg',
        ]
        count = 0
        for pattern in patterns:
            for pkg in self.dist_dir.glob(pattern):
                if stop_requested():
                    print(f"[STOP] Stopping macOS upload loop early", flush=True)
                    return count
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
        print(f"Dist Dir:    {self.dist_dir}")

        # Verify dist directory exists. The wrapper downloads
        # `*-installer` artifacts into `dist/` before invoking us; if
        # we land here without that directory, every build job either
        # failed or produced no artifacts, and there is nothing to
        # upload. Surface that as a hard precondition failure
        # (cf. EXIT_HARD_FAIL) so the CI UI shows a red error rather
        # than silently logging a warning.
        if not self.dist_dir.exists():
            raise _PreconditionError(f"Dist directory not found: {self.dist_dir}")

        # Run all three platform uploaders concurrently. Each method is
        # internally sequential (one package at a time), so we get the same
        # per-file ordering as before but the three platforms no longer wait
        # for each other. Three workers is enough — going higher won't help
        # when the local runner's upload bandwidth is the bottleneck.
        #
        # Drain strategy: `wait(..., timeout=1, return_when=FIRST_COMPLETED)`
        # returns whatever finished in the last 1s window WITHOUT raising
        # `TimeoutError` when only some futures resolved. Earlier we used
        # `as_completed(..., timeout=1)`, which raises `TimeoutError` from
        # its iterator the moment the 1s window expires with any unfinished
        # future left -- and `concurrent.futures.as_completed` propagates
        # that TimeoutError out of the for-loop instead of returning the
        # already-finished ones. In practice that turned into a false
        # "upload failed" exit code whenever one SDK worker took >1s
        # between async yields (e.g. the Windows sha256 round-trip after
        # the .exe part finished), even though every future eventually
        # resolved successfully. See the long comment block in
        # .github/workflows/shared-cos-upload.yml for the wrapper's
        # expectation: rc=1 here makes the step announce "COS upload
        # failed; falling back to GHA artifact URLs" while the artifacts
        # are actually already in COS -- a misleading log line that masks
        # success. The wait()-based drain below fixes that without
        # changing any exit-code contract.
        #
        # We poll the cancellation Event alongside the wait so the main
        # thread doesn't block on a future once SIGTERM arrives. Per-platform
        # workers don't check the Event themselves (they're inside the SDK's
        # blocking upload_file call), but the polling loop above breaks out
        # within ~1s and exits the process -- faster than the 30s SIGKILL
        # grace period, which is what makes "Cancel workflow" feel responsive.
        with ThreadPoolExecutor(max_workers=3, thread_name_prefix="cos-up") as pool:
            futures = {
                pool.submit(self.upload_windows_artifacts, platform_filter): "windows",
                pool.submit(self.upload_macos_artifacts, platform_filter, arch_filter): "macos",
                pool.submit(self.upload_linux_artifacts, platform_filter, arch_filter): "linux",
            }
            counts = {}
            try:
                # Drain whatever finishes first; if cancellation arrives,
                # stop waiting and fall through to cleanup. 1s poll keeps the
                # main thread free to react to SIGTERM promptly.
                while futures:
                    if stop_requested():
                        print("[STOP] Cancellation flag set; abandoning in-flight platform uploads", flush=True)
                        for fut in futures:
                            fut.cancel()
                        break
                    # `wait` returns (done, not_done). `FIRST_COMPLETED`
                    # means the call returns as soon as at least one future
                    # is finished (or the 1s timeout elapses), AND it does
                    # NOT raise TimeoutError when the window expires with
                    # pending work -- unlike `as_completed`. That's the
                    # property we need: the loop re-enters wait() if any
                    # future is still in flight, with no exception to catch.
                    done, _ = wait(futures.keys(), timeout=1, return_when=FIRST_COMPLETED)
                    for fut in done:
                        platform = futures.pop(fut)
                        try:
                            counts[platform] = fut.result()
                        except Exception as e:
                            print(f"[ERROR] {platform} upload crashed: {e}")
                            counts[platform] = 0
                    # Loop again to re-enter wait() for the remaining
                    # futures; the 1s timeout lets us re-check stop_requested.
            finally:
                # Whether we exited cleanly or via cancellation, the executor
                # context manager will wait on the worker threads. They've
                # been backgrounded into SDK sockets that won't respond to
                # SIGTERM, so we don't block on shutdown -- let the runner
                # SIGKILL the process tree if any are still alive.
                pool.shutdown(wait=False, cancel_futures=True)

        if stop_requested():
            print("\n[STOP] Upload aborted by cancellation", flush=True)
            return False

        total = sum(counts.values())
        if total == 0:
            # Builds ran but produced no installable artifacts (e.g.,
            # the pre-built installer / .deb / .pkg never landed in
            # dist/). Same hard-fail semantics as a missing dist
            # directory: there's nothing to upload and the upstream
            # pipeline is broken.
            raise _PreconditionError("No artifacts found to upload")

        print(f"\n[INFO] Uploaded {total} artifact(s) "
              f"(windows={counts.get('windows', 0)}, "
              f"macos={counts.get('macos', 0)}, "
              f"linux={counts.get('linux', 0)})")
        return True


class _PreconditionError(Exception):
    """Raised by COSUploader.upload_all() when a hard precondition fails.

    See COSUploader.EXIT_HARD_FAIL for the contract this exception
    implements (the CLI translates it to exit code 2, which the CI
    wrapper renders as a red `::error::` annotation)."""


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
    parser.add_argument('--dist-dir', default=None,
                        help='Source directory of build artifacts '
                             '(default: <project_root>/dist). Build jobs calling this '
                             'script directly (CN direct-upload fast path) pass the '
                             'platform-specific staging directory, e.g. ``artifacts/``.')

    args = parser.parse_args()
    install_signal_handlers()
    uploader = COSUploader(args.version, args.env, app_id=args.app,
                           dist_dir=args.dist_dir)
    try:
        success = uploader.upload_all(platform_filter=args.platform, arch_filter=args.arch)
    except _PreconditionError as e:
        # Hard precondition failure (missing dist, no artifacts). The
        # GitHub Actions wrapper in shared-cos-upload.yml renders rc=2
        # as a red `::error::` annotation so the failure is visible in
        # the UI instead of buried under a yellow warning. Soft runtime
        # failures (COS unreachable, auth) keep the historical rc=1
        # → ::warning:: contract so transient COS problems don't
        # false-alarm the build.
        if stop_requested():
            # Cancellation supersedes everything — don't pretend a
            # hard precondition failed if the user cancelled mid-run.
            sys.exit(130)
        print(f"[ERROR] {e}")
        sys.exit(COSUploader.EXIT_HARD_FAIL)
    if stop_requested():
        # Exit code 130 mirrors what bash returns when killed by SIGINT, and
        # signals to the workflow runner that this was a cooperative abort,
        # not a real upload failure.
        sys.exit(130)
    sys.exit(COSUploader.EXIT_OK if success else COSUploader.EXIT_SOFT_FAIL)


if __name__ == "__main__":
    main()
