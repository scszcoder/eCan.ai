"""Resolve OTA bucket / region / base-path from the canonical config.

Single source of truth for both the upload side (upload_to_s3.py /
upload_to_cos.py) and the download-links side (shared-download-links.yml /
shared-cos-download-links.yml).

Until this script existed, the upload side read `ota/config/ota_config.yaml`
but the download-links workflow read GitHub secrets (`S3_BUCKET`,
`COS_BUCKET`, etc.). When the secrets were missing the download-links
job silently no-op'd — every Windows/macOS/Linux artifact was uploaded
to the bucket but the `📦 Download Links` step summary was empty.

This script makes both sides agree on `ota_config.yaml`. Run it from a
workflow step and consume its stdout `KEY=VALUE` lines via `>> $GITHUB_ENV`.

Usage
-----
    python3 build_system/scripts/resolve_ota_bucket.py \
        --app cn \
        --env production

Emits lines like:
    OTA_BUCKET=ecan-releases-1251680599
    OTA_REGION=ap-shanghai
    BUCKET_NAME=ecan-releases-1251680599
    BUCKET_REGION=ap-shanghai
    OTA_BASE_PATH=
    OTA_PREFIX=production
    OTA_APP=cn

`BUCKET_NAME` / `BUCKET_REGION` are aliases of `OTA_BUCKET` / `OTA_REGION`
emitted under the names `render_download_links.py` reads. They cannot live
in `jobs.<id>.env:` in the caller workflow because GHA's schema lint
resolves `env.X` against the static job-env dict before any step runs,
so a `BUCKET_NAME: ${{ env.OTA_BUCKET }}` line there trips
"Unrecognized named-value: 'env'". Aliasing them here keeps the renderer
and the workflow agreeing on a single source (`ota_config.yaml`) without
a shell-variable write/read round-trip.

Exit codes
----------
0  Bucket resolved successfully (always writes something to stdout).
1  Missing config file or required field.
2  Environment section missing for `--env`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - the workflows install pyyaml already
    print("[ERROR] PyYAML not installed. Run `pip install pyyaml`.", file=sys.stderr)
    sys.exit(1)


# repo root is two levels up from this script (build_system/scripts/).
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
OTA_CONFIG = REPO_ROOT / "ota" / "config" / "ota_config.yaml"


def _load_config(path: Path) -> dict:
    if not path.exists():
        print(f"[ERROR] OTA config not found: {path}", file=sys.stderr)
        sys.exit(1)
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        print(f"[ERROR] OTA config is malformed: expected dict, got {type(data).__name__}", file=sys.stderr)
        sys.exit(1)
    return data


def resolve(app: str, env: str) -> dict[str, str]:
    """Resolve against the default ota_config.yaml (REPO_ROOT)."""
    return _resolve_from_path(OTA_CONFIG, app, env)


def _resolve_from_path(config_path: Path, app: str, env: str) -> dict[str, str]:
    cfg = _load_config(config_path)
    common = cfg.get("common") or {}
    envs = cfg.get("environments") or {}

    if app == "cn":
        bucket = common.get("cos_bucket")
        region = common.get("cos_region")
        prefix_key = "cos_prefix"
    elif app == "intl":
        bucket = common.get("s3_bucket")
        region = common.get("s3_region")
        prefix_key = "s3_prefix"
    else:
        print(f"[ERROR] Unknown --app '{app}'. Expected 'cn' or 'intl'.", file=sys.stderr)
        sys.exit(1)

    if not bucket:
        which = "cos_bucket" if app == "cn" else "s3_bucket"
        print(f"[ERROR] ota_config.yaml: common.{which} is empty.", file=sys.stderr)
        sys.exit(1)
    if not region:
        which = "cos_region" if app == "cn" else "s3_region"
        print(f"[ERROR] ota_config.yaml: common.{which} is empty.", file=sys.stderr)
        sys.exit(1)

    env_cfg = envs.get(env)
    if not isinstance(env_cfg, dict):
        print(
            f"[ERROR] ota_config.yaml: environments.{env} is missing. "
            f"Available: {', '.join(sorted(envs)) or '<none>'}",
            file=sys.stderr,
        )
        sys.exit(2)

    prefix = env_cfg.get(prefix_key) or ""

    return {
        "OTA_BUCKET": str(bucket),
        "OTA_REGION": str(region),
        # Aliases consumed by `render_download_links.py`. See module
        # docstring for why they're emitted here rather than echoed
        # separately by the caller workflow.
        "BUCKET_NAME": str(bucket),
        "BUCKET_REGION": str(region),
        "OTA_PREFIX": str(prefix),
        "OTA_BASE_PATH": str(common.get("s3_base_path") or ""),
        "OTA_APP": app,
        "OTA_ENV": env,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument(
        "--app",
        required=True,
        choices=("cn", "intl"),
        help="App identifier — 'cn' reads COS settings, 'intl' reads S3 settings.",
    )
    parser.add_argument(
        "--env",
        required=True,
        help="OTA environment (development/test/staging/production/simulation).",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=OTA_CONFIG,
        help=f"Path to ota_config.yaml (default: {OTA_CONFIG}).",
    )
    args = parser.parse_args()

    cfg_path = args.config
    resolved = _resolve_from_path(cfg_path, args.app, args.env)
    for key, value in resolved.items():
        # GITHUB_ENV / POSIX env files: KEY=VALUE, no quoting, no spaces.
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())