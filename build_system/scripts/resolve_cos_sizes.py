"""Resolve COS object sizes via HeadObject for direct-uploaded artifacts.

Used by `.github/workflows/shared-cos-download-links.yml` when the
Windows (or other) build job took the direct-upload fast path. The
GHA artifact store doesn't have the file in that case — but COS does,
and `HeadObject` returns the authoritative size without downloading the
bytes.

Usage
-----
    python3 build_system/scripts/resolve_cos_sizes.py \
        --app-name eCan.cn \
        --version 0.7.0-lq_dev_multi-ca3fb6c \
        --env-prefix test \
        --bucket ecan-releases-1251680599 \
        --region ap-shanghai \
        --expected \
            windows/amd64/eCan.cn-0.7.0-...-Setup.exe \
            macos/amd64/eCan.cn-0.7.0-...pkg \
            macos/aarch64/eCan.cn-0.7.0-...pkg \
            linux/amd64/eCan.cn-0.7.0-...deb

Emits (stdout) one line per probed object:
    test/releases/v0.7.0-.../windows/amd64/eCan.cn-0.7.0-...-Setup.exe=145823441

When the object doesn't exist (e.g. Linux build was skipped, the script
was given a stale key), the line is omitted. Download-links renders
"missing" for those rows.

Exit codes
----------
0  At least one size was resolved (or no probes were requested).
1  Configuration error (missing secret, missing config).
2  All probes failed at the SDK layer.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

try:
    from qcloud_cos import CosConfig, CosS3Client
except ImportError:  # pragma: no cover - workflow installs this already
    print("[ERROR] cos-python-sdk-v5 not installed. Run `pip install -r "
          "build_system/scripts/requirements-cos.txt`.", file=sys.stderr)
    sys.exit(1)


def _build_client(bucket_region: str) -> CosS3Client:
    secret_id = os.environ.get("ECAN_TENCENT_SECRET_ID", "")
    secret_key = os.environ.get("ECAN_TENCENT_SECRET_KEY", "")
    if not secret_id or secret_key == "":
        print("[ERROR] ECAN_TENCENT_SECRET_ID / ECAN_TENCENT_SECRET_KEY must be set.",
              file=sys.stderr)
        sys.exit(1)

    cos_region_map = {
        "ap-beijing": "ap-beijing-1",
        "ap-shanghai": "ap-shanghai",
        "ap-nanjing": "ap-nanjing-1",
    }
    cos_region = cos_region_map.get(bucket_region, bucket_region)
    try:
        from utils.storage.cos_endpoints import accelerated_endpoint
        cos_endpoint = accelerated_endpoint()
    except Exception:
        cos_endpoint = None

    kwargs = dict(
        Region=cos_region,
        SecretId=secret_id,
        SecretKey=secret_key,
        Timeout=30,
    )
    if cos_endpoint:
        kwargs["Endpoint"] = cos_endpoint
    config = CosConfig(**kwargs)
    return CosS3Client(config, retry=2)


def _head_object(client: CosS3Client, bucket: str, key: str) -> int | None:
    """Return Content-Length for *key*, or None on 404 / network error."""
    try:
        resp = client.head_object(Bucket=bucket, Key=key)
    except Exception as e:
        # 404 means the build for this arch was skipped — not an error.
        code = getattr(e, "get_code", lambda: "")()
        status = getattr(e, "status", lambda: 200)() if hasattr(e, "status") else None
        if code in ("NoSuchKey", "404") or status == 404:
            return None
        # Anything else: log once and bail.
        print(f"[WARN] HeadObject failed for {key}: {e}", file=sys.stderr)
        return None
    headers = getattr(resp, "headers", {}) or {}
    cl = headers.get("Content-Length") or headers.get("content-length")
    if cl is None:
        # Some SDK versions return a dict directly.
        if isinstance(resp, dict):
            cl = resp.get("Content-Length") or resp.get("ContentLength")
    if cl is None:
        return None
    try:
        return int(cl)
    except (TypeError, ValueError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--env-prefix", required=True,
                        help="COS prefix (dev/test/staging/production/...).")
    parser.add_argument("--version", required=True)
    parser.add_argument("--user-prefix", default="",
                        help="Lowercase user-prefix segment for per-user "
                             "preview builds (e.g. 'songc' produces "
                             "'songc_v<version>'). Must match what "
                             "upload_to_cos.py wrote, otherwise HeadObject "
                             "404s. Default '' = regular semver/branch build.")
    parser.add_argument("--expected", nargs="+", default=[],
                        help="Relative object keys (without the prefix / "
                             "version part), e.g. "
                             "'windows/amd64/eCan.cn-...-Setup.exe'.")
    parser.add_argument("--out", default="-",
                        help="File path to write the key=bytes lines to. "
                             "Default '-' = stdout.")
    args = parser.parse_args()

    # Mirrors upload_to_cos.py — both sides must agree on the on-bucket
    # directory name or HeadObject will 404.
    release_dir = (
        f"{args.user_prefix}_v{args.version}"
        if args.user_prefix else f"v{args.version}"
    )
    client = _build_client(args.region)
    resolved = 0
    failures = 0
    lines: list[str] = []

    for rel in args.expected:
        # rel is "platform/arch/filename"; prepend the env prefix and
        # the release directory to form the full COS key.
        rel = rel.lstrip("/")
        key = f"{args.env_prefix}/releases/{release_dir}/{rel}"
        size = _head_object(client, args.bucket, key)
        if size is None:
            failures += 1
            continue
        lines.append(f"{key}={size}")
        resolved += 1

    out_text = "\n".join(lines) + ("\n" if lines else "")
    if args.out == "-":
        sys.stdout.write(out_text)
    else:
        Path(args.out).write_text(out_text, encoding="utf-8")

    if resolved == 0 and args.expected:
        # All probes failed AND we asked for at least one — surface to caller.
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
