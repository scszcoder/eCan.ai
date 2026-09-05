"""Resolve S3 object sizes via HeadObject for direct-uploaded artifacts.

S3 mirror of `resolve_cos_sizes.py`. Used by
`.github/workflows/shared-download-links.yml` when a build job took the
intl direct-upload fast path.

Usage
-----
    python3 build_system/scripts/resolve_s3_sizes.py \
        --bucket ecan-releases \
        --region us-east-1 \
        --env-prefix test \
        --version 0.7.0-lq_dev_multi-ca3fb6c \
        --expected windows/amd64/eCan-...Setup.exe ...

Exit codes: same as the COS variant.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

try:
    import boto3
    from botocore.exceptions import ClientError
except ImportError:  # pragma: no cover - workflow installs this already
    print("[ERROR] boto3 not installed. Run `pip install -r "
          "build_system/scripts/requirements.txt`.", file=sys.stderr)
    sys.exit(1)


def _build_client(region: str):
    key_id = os.environ.get("AWS_ACCESS_KEY_ID", "")
    secret = os.environ.get("AWS_SECRET_ACCESS_KEY", "")
    if not key_id or not secret:
        print("[ERROR] AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY must be set.",
              file=sys.stderr)
        sys.exit(1)
    return boto3.client(
        "s3",
        region_name=region,
        aws_access_key_id=key_id,
        aws_secret_access_key=secret,
    )


def _head_object(client, bucket: str, key: str) -> int | None:
    try:
        resp = client.head_object(Bucket=bucket, Key=key)
    except ClientError as e:
        code = (e.response.get("Error") or {}).get("Code", "")
        if code in ("404", "NoSuchKey", "NotFound"):
            return None
        print(f"[WARN] HeadObject failed for {key}: {e}", file=sys.stderr)
        return None
    cl = resp.get("ContentLength")
    return int(cl) if cl is not None else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--env-prefix", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--expected", nargs="+", default=[])
    parser.add_argument("--out", default="-")
    args = parser.parse_args()

    client = _build_client(args.region)
    resolved = 0
    lines: list[str] = []
    for rel in args.expected:
        rel = rel.lstrip("/")
        key = f"{args.env_prefix}/releases/v{args.version}/{rel}"
        size = _head_object(client, args.bucket, key)
        if size is None:
            continue
        lines.append(f"{key}={size}")
        resolved += 1

    out_text = "\n".join(lines) + ("\n" if lines else "")
    if args.out == "-":
        sys.stdout.write(out_text)
    else:
        Path(args.out).write_text(out_text, encoding="utf-8")
    if resolved == 0 and args.expected:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
