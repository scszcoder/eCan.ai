#!/usr/bin/env python3
"""
One-shot diagnostic: measure real upload throughput from local mac ->
COS ap-shanghai using the same PartSize/MAXThread policy as the fix.

Run:
    export ECAN_TENCENT_SECRET_ID=...
    export ECAN_TENCENT_SECRET_KEY=...
    python3 scripts/dev/measure_cos_throughput.py [--size-mb 60]

Why a standalone script
------------------------
``tests/e2e/test_cos_upload_large.py`` is gated behind pytest+credentials
and is built for CI. For an interactive "is my local network fast enough
for the GHA runner?" check, dropping into a 50-line script and printing
timings inline is faster than wiring fixtures. Reuses the same SDK
constants as ``upload_to_cos.py`` so the numbers are comparable.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import secrets
import sys
import time
import uuid
from pathlib import Path

# Repo root on sys.path so we can import the canonical chunk_params_for
# (matches what upload_to_cos.py will pick at runtime).
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

try:
    from qcloud_cos import CosConfig, CosS3Client
    from qcloud_cos.cos_exception import CosServiceError
except ImportError:
    sys.exit("cos-python-sdk-v5 not installed. pip install -r requirements-cn.txt")

from build_system.scripts.upload_to_cos import chunk_params_for  # noqa: E402


_REGION_ALIAS = {"ap-beijing": "ap-beijing-1", "ap-shanghai": "ap-shanghai"}


def _client(bucket: str, region: str, sid: str, skey: str) -> CosS3Client:
    cfg = CosConfig(
        Region=_REGION_ALIAS.get(region, region),
        SecretId=sid,
        SecretKey=skey,
        Timeout=120,  # match upload_to_cos.py
    )
    return CosS3Client(cfg, retry=5)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--size-mb", type=int, default=60,
                   help="payload size in MB (default 60)")
    p.add_argument("--bucket", default=os.environ.get("ECAN_COS_E2E_BUCKET", "ecan-skills-1251680599"))
    p.add_argument("--region", default=os.environ.get("ECAN_COS_E2E_REGION", "ap-shanghai"))
    p.add_argument("--prefix", default=os.environ.get(
        "ECAN_COS_E2E_PREFIX",
        f"throughput_probe_{os.environ.get('USER', 'local')}_{int(time.time())}/",
    ).rstrip("/") + "/")
    p.add_argument("--keep", action="store_true",
                   help="don't delete the uploaded key after success")
    args = p.parse_args()

    sid = os.environ.get("ECAN_TENCENT_SECRET_ID", "")
    skey = os.environ.get("ECAN_TENCENT_SECRET_KEY", "")
    if not sid or not skey:
        sys.exit("Set ECAN_TENCENT_SECRET_ID and ECAN_TENCENT_SECRET_KEY first.")

    # 1. Generate payload
    size_bytes = args.size_mb * 1024 * 1024
    payload = Path(f"/tmp/cos_probe_{uuid.uuid4().hex}.bin")
    print(f"[1/4] Generating {args.size_mb}MB random payload at {payload} ...")
    t0 = time.monotonic()
    chunk = 1024 * 1024
    with open(payload, "wb") as f:
        remaining = size_bytes
        while remaining > 0:
            n = min(chunk, remaining)
            f.write(secrets.token_bytes(n))
            remaining -= n
    gen_elapsed = time.monotonic() - t0
    print(f"      done in {gen_elapsed:.2f}s "
          f"({size_bytes / gen_elapsed / (1024*1024):.1f} MB/s local write)")

    # 2. SHA256 (sanity check; also matches production path)
    sha = hashlib.sha256()
    with open(payload, "rb") as f:
        for blk in iter(lambda: f.read(1024 * 1024), b""):
            sha.update(blk)
    src_sha = sha.hexdigest()
    print(f"[2/4] SHA256: {src_sha}")

    # 3. Upload with production-equivalent params
    part_size_mb, max_thread = chunk_params_for(args.size_mb)
    parts_expected = max(1, -(-args.size_mb // part_size_mb))  # ceil
    key = f"{args.prefix}{payload.name}"
    client = _client(args.bucket, args.region, sid, skey)

    print(f"[3/4] Uploading to cos://{args.bucket}/{key}")
    print(f"      PartSize={part_size_mb}MB  MAXThread={max_thread}  "
          f"~{parts_expected} parts expected")
    t0 = time.monotonic()
    try:
        client.upload_file(
            Bucket=args.bucket,
            Key=key,
            LocalFilePath=str(payload),
            PartSize=part_size_mb,
            MAXThread=max_thread,
            EnableMD5=False,
        )
    except CosServiceError as e:
        print(f"      FAILED: {e.get_error_code()} - {e.get_error_msg()}")
        payload.unlink(missing_ok=True)
        return 2
    upload_elapsed = time.monotonic() - t0
    throughput_mbps = (size_bytes / upload_elapsed) / (1024 * 1024)
    print(f"      done in {upload_elapsed:.2f}s -> {throughput_mbps:.2f} MB/s")

    # 4. Round-trip SHA256 to catch silent corruption
    print("[4/4] Downloading and verifying SHA256 round-trip ...")
    downloaded = payload.with_suffix(".downloaded")
    t0 = time.monotonic()
    client.download_file(
        Bucket=args.bucket,
        Key=key,
        DestFilePath=str(downloaded),
    )
    dl_elapsed = time.monotonic() - t0
    sha = hashlib.sha256()
    with open(downloaded, "rb") as f:
        for blk in iter(lambda: f.read(1024 * 1024), b""):
            sha.update(blk)
    rt_sha = sha.hexdigest()
    dl_throughput = (size_bytes / dl_elapsed) / (1024 * 1024)
    print(f"      download: {dl_elapsed:.2f}s -> {dl_throughput:.2f} MB/s")
    print(f"      SHA256 match: {rt_sha == src_sha}")

    # Cleanup
    payload.unlink(missing_ok=True)
    downloaded.unlink(missing_ok=True)
    if not args.keep:
        try:
            client.delete_object(Bucket=args.bucket, Key=key)
            print(f"      cleanup: deleted {key}")
        except Exception as e:
            print(f"      cleanup failed (manual): {e}")

    # Summary
    print("\n=== Summary ===")
    print(f"Payload:        {args.size_mb}MB")
    print(f"Upload time:    {upload_elapsed:.2f}s")
    print(f"Upload speed:   {throughput_mbps:.2f} MB/s ({throughput_mbps*8:.1f} Mbps)")
    print(f"Extrapolated 600MB: {600 / throughput_mbps:.0f}s "
          f"({600 / throughput_mbps / 60:.1f} min)")
    print(f"SHA256 round-trip OK: {rt_sha == src_sha}")

    return 0 if rt_sha == src_sha else 3


if __name__ == "__main__":
    sys.exit(main())