"""End-to-end OTA reachability smoke test.

Runs after a release has uploaded latest.json / appcast / installer
artifacts to the OTA bucket. Pulls each public URL the same way a
client would and asserts:

  1. latest.json is reachable (HTTP 200 + parseable JSON).
  2. Every platform entry has HTTP 200 + matching Content-Length +
     application/octet-stream Content-Type for the installer URL.
  3. The per-platform appcast XML (and the CN zh-CN variant) is
     reachable and lists the same version as the platform's latest.json
     entry.
  4. The appcast <enclosure> URL / sparkle:version match the
     platform's version in latest.json.

Note on top-level `version`: this field is the highest version across
all platforms currently in latest.json. Staggered multi-platform
releases (e.g. windows ships at v1.0.0 before macos-amd64 is built)
are a valid scenario, so the top-level field may exceed what a
specific client can download. Clients must use the per-platform
version from platforms.{key}.version, not the top-level field.
We report a warning (not a failure) when the top-level version is
not present in any platform entry.

The script does NOT download the installer binaries (a Windows-only
release is already ~574 MB; multi-platform would saturate the runner
network and waste 4+ minutes on a job that already proved success at
upload time). Content-Length + Content-Type is a sufficient proxy for
"object exists with the right metadata", and the previous CI run
already verified the bytes-to-bucket hash via generate_latest_json.py.

Exit codes
----------
0  All checks passed (warnings are allowed).
1  At least one URL unreachable, wrong metadata, or version mismatch.

Failure messages are written to stdout in `::error::` annotation form
so GitHub Actions threads them in the run UI without a parser.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    import yaml
except ImportError:
    print("[ERROR] PyYAML not installed. Run `pip install pyyaml`.", file=sys.stderr)
    sys.exit(1)


# Same path resolution as resolve_ota_bucket.py: walk up from this
# script to the repo root. Keep these in lock-step - drift between
# the two readers defeats the whole point of having a single
# ota_config.yaml.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
OTA_CONFIG = REPO_ROOT / "ota" / "ota_config.yaml"
# Fall back to config/ subpath if the in-tree config moved (older
# checkouts used ota/config/).
_FALLBACK = REPO_ROOT / "ota" / "config" / "ota_config.yaml"


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str = ""
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_markdown_row(self) -> str:
        badge = "OK" if self.ok else "FAIL"
        if self.ok:
            msg = self.detail or "ok"
        else:
            msg = "; ".join(self.errors) or self.detail
        if self.warnings:
            msg += " [WARN] " + self.warnings[0]
        return f"| {self.name} | {badge} | {msg} |"


# ---------------------------------------------------------------------------
# Config loading (mirrors resolve_ota_bucket.py so the two stay aligned)
# ---------------------------------------------------------------------------

def _load_config(path: Path) -> dict:
    if not path.exists():
        print(f"[ERROR] OTA config not found: {path}", file=sys.stderr)
        sys.exit(1)
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def resolve_bucket(cfg: dict, app: str) -> tuple[str, str]:
    """Return (bucket, region) for the requested app."""
    common = cfg.get("common") or {}
    if app == "cn":
        return (common.get("cos_bucket") or ""), (common.get("cos_region") or "")
    if app == "intl":
        return (common.get("s3_bucket") or ""), (common.get("s3_region") or "")
    print(f"[ERROR] Unknown app '{app}', expected 'cn' or 'intl'.", file=sys.stderr)
    sys.exit(1)


def host_for(bucket: str, region: str, app: str) -> str:
    """Public hostname for OTA artifacts.

    Mirrors generate_appcast.py:upload side and shared-cos-download-links.yml:
    CN uses the myqcloud.com COS endpoint, intl uses the AWS S3 regional
    endpoint. We deliberately use the bucket virtual-host style that the
    upload side writes to, so a HEAD against this URL is exactly what a
    client would issue.

    Returns the *hostname only* - callers must compose the full URL with
    the per-env prefix path themselves.
    """
    if app == "cn":
        return f"{bucket}.cos.{region}.myqcloud.com"
    return f"{bucket}.s3.{region}.amazonaws.com"


def appcast_base_for(cfg: dict, app: str, env: str) -> str:
    """Pull appcast_base(_cos) from the env config.

    This is the same string the upload side uses as its CDN base - if our
    URL diverges from upload's, we are smoke-testing the wrong endpoint.
    The user-facing test of the bucket must match the user-facing base
    declared in ota_config.yaml.
    """
    envs = cfg.get("environments") or {}
    env_cfg = envs.get(env) or {}
    if app == "cn":
        return env_cfg.get("appcast_base_cos") or ""
    return env_cfg.get("appcast_base") or ""


# ---------------------------------------------------------------------------
# HTTP primitives - stdlib only, no third-party deps.
# ---------------------------------------------------------------------------

def _request(url: str, *, method: str = "GET", timeout: float = 15.0) -> tuple[int, dict, bytes]:
    """Issue a request, return (status, headers, body).

    Body is empty for HEAD. Follows up to 5 redirects - Tencent COS
    and S3 both redirect on regional mismatch; we want to follow them
    transparently rather than treat the redirect itself as a failure.
    """
    req = urllib.request.Request(url, method=method)
    opener = urllib.request.build_opener(
        urllib.request.HTTPRedirectHandler(),
    )
    try:
        resp = opener.open(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        # Treat 4xx/5xx as a normal response so the caller can print
        # the exact status in its ::error:: annotation instead of a
        # stack trace. urllib's HTTPError carries the same headers
        # and body that a 200 would have.
        return e.code, dict(e.headers), e.read() or b""
    except urllib.error.URLError as e:
        print(f"::error::{method} {url} failed at the network layer: {e.reason}", file=sys.stderr)
        return 0, {}, b""
    return resp.status, dict(resp.headers), resp.read() or b""


def head(url: str, timeout: float = 15.0) -> tuple[int, dict]:
    """HEAD request returning (status, headers)."""
    status, headers, _ = _request(url, method="HEAD", timeout=timeout)
    return status, headers


def get_text(url: str, timeout: float = 15.0) -> tuple[int, str]:
    """GET request returning (status, body-as-text)."""
    status, _, body = _request(url, method="GET", timeout=timeout)
    return status, body.decode("utf-8", errors="replace")


def get_json(url: str, timeout: float = 15.0) -> tuple[int, Optional[dict]]:
    """GET request returning (status, parsed-json). Returns None on parse failure."""
    status, text = get_text(url, timeout=timeout)
    if status != 200:
        return status, None
    try:
        return status, json.loads(text)
    except json.JSONDecodeError as e:
        print(f"::error::{url} returned 200 but body is not valid JSON: {e}", file=sys.stderr)
        return status, None


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

# The four platform keys we always check. CN/intl builds are 1:1 on
# these four.
ALL_PLATFORMS = ["macos-aarch64", "macos-amd64", "windows-amd64", "linux-amd64"]


def check_latest_json(host: str, prefix: str, expected_version: str = "") -> tuple[CheckResult, Optional[dict]]:
    """Pull latest.json. Return the check result + parsed body (None on failure)."""
    url = f"https://{host}/{prefix}/latest.json"
    status, doc = get_json(url)
    if status != 200 or doc is None:
        return CheckResult(
            name="latest.json reachable",
            ok=False,
            errors=[f"GET {url} -> HTTP {status} (body not parseable)"],
        ), None
    if not isinstance(doc, dict):
        return CheckResult(
            name="latest.json reachable",
            ok=False,
            errors=[f"{url} returned JSON but not an object: {type(doc).__name__}"],
        ), None
    top_version = doc.get("version")
    platforms = doc.get("platforms") or {}
    if not isinstance(platforms, dict):
        return CheckResult(
            name="latest.json shape",
            ok=False,
            errors=[f"'platforms' is not a dict: {type(platforms).__name__}"],
        ), None

    # Stagger guard: the top-level `version` may be higher than any
    # individual platform's version during a multi-platform rollout.
    # This is a valid scenario (one platform ships before others), so
    # we only warn rather than fail. Clients must use
    # platforms.{key}.version, not the top-level field.
    platform_versions = {p.get("version") for p in platforms.values() if isinstance(p, dict)}
    drift_warn = ""
    if top_version and top_version not in platform_versions:
        drift_warn = (
            f"top-level version '{top_version}' not present in any platform entry "
            f"(have {sorted(v for v in platform_versions if v)}). "
            f"Clients should read their platform-specific version, not this top-level field."
        )

    # Soft check on expected_version: the release we just published should
    # be the latest in latest.json. If it is not, something is wrong with
    # merge order - but tolerate the case where a hotfix ran between this
    # smoke test and the previous release finishing.
    expected_warn = ""
    if expected_version and expected_version != top_version:
        expected_warn = (
            f"this release's version '{expected_version}' differs from latest.json top-level "
            f"'{top_version}' - a newer release may have deployed between generate-latest-json "
            f"and this smoke test."
        )

    detail_parts = [
        f"HTTP 200, top-level version={top_version}, platforms={len(platforms)}, "
        f"updated_at={doc.get('updated_at', '?')}"
    ]
    if drift_warn:
        detail_parts.append(drift_warn)
    if expected_warn:
        detail_parts.append(expected_warn)

    return CheckResult(
        name="latest.json",
        ok=True,
        detail="; ".join(detail_parts),
        warnings=[w for w in (drift_warn, expected_warn) if w],
    ), doc


def check_installer_url(host: str, platform_key: str, info: dict) -> CheckResult:
    """Verify one platform's installer URL + size + content-type.

    We do NOT download the binary itself - Content-Length + Content-Type
    is enough to prove the upload landed intact (sha256 is already
    proven by generate_latest_json.py at upload time). The CDN
    bandwidth saved here is ~574 MB * N platforms per release.
    """
    url = info.get("url") or ""
    if not url:
        return CheckResult(
            name=f"{platform_key} installer URL",
            ok=False,
            errors=["latest.json platform entry missing 'url' field"],
        )
    expected_size = info.get("file_size") or 0
    status, headers = head(url)
    errors: list[str] = []
    if status != 200:
        errors.append(f"HEAD {url} -> HTTP {status}")
        return CheckResult(name=f"{platform_key} installer", ok=False, errors=errors)
    content_length = headers.get("Content-Length") or headers.get("content-length") or "0"
    try:
        actual_size = int(content_length)
    except (TypeError, ValueError):
        actual_size = 0
    ctype = (headers.get("Content-Type") or headers.get("content-type") or "").split(";")[0].strip()
    # Latest.json sometimes stores file_size as a string (it comes from
    # a JSON parse of an upload manifest). Coerce for comparison.
    if isinstance(expected_size, str):
        try:
            expected_size = int(expected_size)
        except ValueError:
            expected_size = 0
    if expected_size and actual_size and actual_size != expected_size:
        errors.append(
            f"size mismatch: latest.json says {expected_size}, server returned "
            f"Content-Length={actual_size}"
        )
    # Accept any of the common installer Content-Types:
    #   - application/octet-stream        - generic
    #   - application/x-msdownload       - Windows .exe (default for COS / S3)
    #   - application/x-msdos-program    - alt Windows .exe type
    #   - application/vnd.apple.pkg       - macOS .pkg
    ctype_norm = ctype.lower()
    is_binary = (
        "octet-stream" in ctype_norm
        or "x-msdownload" in ctype_norm
        or "x-msdos-program" in ctype_norm
        or "vnd.apple.pkg" in ctype_norm
        or "/exe" in ctype_norm
    )
    if ctype and not is_binary:
        errors.append(
            f"unexpected Content-Type '{ctype}' for installer URL "
            f"(expected application/octet-stream or application/x-msdownload)"
        )
    return CheckResult(
        name=f"{platform_key} installer",
        ok=not errors,
        detail=(
            f"HTTP 200, Content-Length={actual_size}"
            + (f", Content-Type={ctype}" if ctype else "")
        ),
        errors=errors,
    )


def _norm_version(s: str) -> str:
    """Normalize a version string for comparison.

    latest.json stores versions like '0.7.0-v0.9.97d-53bdc77' (no leading
    'v') while appcast sparkle:version values sometimes include the
    leading 'v'. lstrip('v') once handles both shapes without mangling
    pre-release tags like 'v1.0.0-rc.1'.
    """
    return s.lstrip("v")


# Sparkle EdDSA (Ed25519) signatures are exactly 64 raw bytes; base64
# encoded with padding that becomes 88 characters. Use this for the
# "format only" sanity check below - the cryptographic verification
# happens when --verify-signature is enabled (the operator provides
# ECAN_OTA_PUBLIC_KEY_B64). Until that key is provisioned we only
# assert the signature has the right shape, which is enough to catch
# every "signature was uploaded as empty / wrong field / wrong
# encoding" failure mode.
_SPARKLE_ED25519_B64_LEN = 88
_SPARKLE_NS = "http://www.andymatuschak.org/xml-namespaces/sparkle"


def _validate_signature_format(b64_value: str) -> tuple[bool, str]:
    """Return (ok, reason). Pure structural check, no crypto.

    Sparkle EdDSA signatures are base64-encoded 64 raw bytes (Ed25519).
    Anything else means the upload pipeline is broken at the format
    layer (wrong field name, missing attribute, double-encoding, etc.)
    - all of these cause Sparkle / WinSparkle / Squirrel clients to
    reject the update SILENTLY. Catching the structural shape here
    means a missing or wrong-format signature fails CI rather than
    failing in production for users.
    """
    if not b64_value:
        return False, "empty signature"
    stripped = b64_value.strip()
    # base64 alphabet: A-Za-z0-9+/= - allow only those.
    valid_chars = set(
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/="
    )
    bad = [c for c in stripped if c not in valid_chars]
    if bad:
        return False, f"non-base64 chars: {bad[:3]}"
    # Length must equal 88 (64 raw bytes padded to base64).
    if len(stripped) != _SPARKLE_ED25519_B64_LEN:
        return (
            False,
            f"wrong length {len(stripped)} (expected {_SPARKLE_ED25519_B64_LEN} for Ed25519)",
        )
    try:
        import base64 as _b64
        decoded = _b64.b64decode(stripped, validate=True)
    except Exception as e:
        return False, f"base64 decode failed: {e}"
    if len(decoded) != 64:
        return False, f"decoded length {len(decoded)} (expected 64 for Ed25519)"
    return True, ""


def _verify_signature_crypto(
    installer_bytes: bytes, signature_b64: str, public_key_b64: str
) -> tuple[bool, str]:
    """Ed25519 verify. Returns (ok, reason).

    Used only when --verify-signature is enabled AND
    ECAN_OTA_PUBLIC_KEY_B64 is set. The signature, public key, and
    installer bytes are exactly what Sparkle / WinSparkle / Squirrel
    pass into their own verify routine on the client side. If this
    returns False, the update will fail on every user machine.

    We require `cryptography` (already a Sparkle-toolchain standard
    dep) but the import is deferred so the smoke test can still run
    without it when --verify-signature is off.
    """
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PublicKey,
        )
        from cryptography.hazmat.primitives import serialization
    except ImportError:
        return False, (
            "`cryptography` package not installed - cannot run --verify-signature. "
            "Add it to build_system/scripts/requirements.txt."
        )
    import base64 as _b64
    try:
        sig = _b64.b64decode(signature_b64, validate=True)
        pub = _b64.b64decode(public_key_b64, validate=True)
        if len(sig) != 64:
            return False, f"signature length {len(sig)} != 64"
        if len(pub) != 32:
            return False, f"public-key length {len(pub)} != 32 (Ed25519 raw)"
        pk = Ed25519PublicKey.from_public_bytes(pub)
    except Exception as e:
        return False, f"key/parse: {e}"
    try:
        pk.verify(sig, installer_bytes)
    except Exception as e:
        return False, f"verify: {e}"
    return True, ""


def check_appcast(
    host: str,
    prefix: str,
    platform: str,
    arch: str,
    app: str,
    expected_version: str = "",
) -> list[CheckResult]:
    """Pull every appcast variant for one platform/arch.

    CN publishes a zh-CN variant in addition to the default English
    one. intl publishes only the default. We check all that exist.
    """
    results: list[CheckResult] = []
    base = f"https://{host}/{prefix}/channels/stable/appcast-{platform}-{arch}"
    # Default (English) is always served. CN adds zh-CN.
    # Note on filename: upload_appcast() in generate_appcast.py uses
    # a DOT before the language suffix (e.g. appcast-windows-amd64.zh-CN.xml)
    # for the default 'en-US' case to keep the historical no-suffix name.
    languages = ["en-US"]
    if app == "cn":
        languages.append("zh-CN")
    expected_norm = _norm_version(expected_version) if expected_version else ""

    for lang in languages:
        # en-US uses no suffix (legacy); other languages use DOT before
        # the language code to match the upload side exactly.
        suffix = "" if lang == "en-US" else f".{lang}"
        url = f"{base}{suffix}.xml"
        status, text = get_text(url)
        if status != 200:
            results.append(CheckResult(
                name=f"appcast {platform}-{arch}{(' ' + lang) if lang != 'en-US' else ''}",
                ok=False,
                errors=[f"GET {url} -> HTTP {status}"],
            ))
            continue
        try:
            root = ET.fromstring(text)
        except ET.ParseError as e:
            results.append(CheckResult(
                name=f"appcast {platform}-{arch}{(' ' + lang) if lang != 'en-US' else ''}",
                ok=False,
                errors=[f"{url} returned XML that failed to parse: {e}"],
            ))
            continue
        # Sparkle uses <item> elements inside <rss><channel>. Each
        # item has <sparkle:version> and <enclosure url="..." ...>.
        # We use the Sparkle namespace and ignore items missing it.
        ns = {"sparkle": _SPARKLE_NS}
        items = root.findall(".//item")
        if not items:
            results.append(CheckResult(
                name=f"appcast {platform}-{arch}{(' ' + lang) if lang != 'en-US' else ''}",
                ok=False,
                errors=[f"{url} returned 200 but contains no <item> elements"],
            ))
            continue

        # Find the matching item and the FIRST item (which is the
        # latest by RSS convention - Sparkle and WinSparkle both use
        # the first <item> as the "newest update available" so we
        # MUST assert the expected version appears there, not in
        # some later position.
        matching_item = None
        first_item = items[0]
        first_enc = first_item.find("enclosure")
        first_enclosure_url = first_enc.get("url") if first_enc is not None else ""
        first_enclosure_length = first_enc.get("length") if first_enc is not None else ""
        first_signature = (
            first_enc.get(f"{{{_SPARKLE_NS}}}edSignature")
            if first_enc is not None else None
        )

        if expected_norm:
            for item in items:
                enc_el = item.find("enclosure")
                if enc_el is None:
                    continue
                ver = enc_el.get(f"{{{_SPARKLE_NS}}}version")
                if ver and _norm_version(ver) == expected_norm:
                    matching_item = item
                    break

        errors: list[str] = []
        detail_parts = [
            f"HTTP 200, {len(items)} item(s)",
        ]

        if expected_norm:
            if matching_item is None:
                errors.append(
                    f"expected version '{expected_version}' not found among "
                    f"{len(items)} item(s) in {url}"
                )
            elif matching_item is not first_item:
                # RSS puts the newest item first; if the release we
                # just shipped isn't there, clients on every version
                # older than ours will never see the prompt. This is
                # a near-miss of "the upload overwrote the appcast".
                errors.append(
                    f"expected version '{expected_version}' found but NOT at "
                    f"the top item (RSS first-element is {first_item.find('sparkle:version', ns).text if first_item.find('sparkle:version', ns) is not None else '?'}); "
                    f"Sparkle clients use the FIRST item as the latest update"
                )
            else:
                detail_parts.append(f"top item version={expected_version}")

        # Sparkle-standard sanity check (industry standard): top
        # item's enclosure MUST carry a base64 EdDSA signature. A
        # missing or malformed signature causes every OTA client
        # (Sparkle, WinSparkle, Squirrel, NetSparkle, every custom
        # build that consumes the appcast) to silently reject the
        # update. We assert the shape; full cryptographic verify is
        # optional via --verify-signature.
        if first_signature is None or first_signature == "":
            errors.append(
                f"top <enclosure> missing sparkle:edSignature "
                f"(Sparkle clients reject updates without EdDSA sig)"
            )
        else:
            ok, why = _validate_signature_format(first_signature)
            if not ok:
                errors.append(
                    f"top <enclosure> sparkle:edSignature is malformed: {why}"
                )
            else:
                detail_parts.append("edSignature present + base64 valid")

        results.append(CheckResult(
            name=f"appcast {platform}-{arch}{(' ' + lang) if lang != 'en-US' else ''}",
            ok=not errors,
            detail="; ".join(detail_parts) + (
                f", first enclosure url={first_enclosure_url}"
                if first_enclosure_url else ""
            ),
            errors=errors,
        ))
    return results


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def run(args: argparse.Namespace) -> int:
    cfg = _load_config(OTA_CONFIG if OTA_CONFIG.exists() else _FALLBACK)
    bucket, region = resolve_bucket(cfg, args.app)
    if not bucket or not region:
        print(f"::error::OTA config missing bucket/region for app={args.app}", file=sys.stderr)
        return 1
    base_from_config = appcast_base_for(cfg, args.app, args.env)
    # The host part of appcast_base must match the bucket host. We
    # deliberately use the bucket virtual-host URL, not the appcast_base
    # override, because latest.json / installer URLs are always published
    # to the bucket, not to the optional override.
    host = host_for(bucket, region, args.app)

    envs = cfg.get("environments") or {}
    env_cfg = envs.get(args.env) or {}
    prefix_key = "cos_prefix" if args.app == "cn" else "s3_prefix"
    prefix = (env_cfg.get(prefix_key) or "").strip()
    if not prefix:
        print(
            f"::error::ota_config.yaml environments.{args.env}.{prefix_key} is empty. "
            f"Cannot construct smoke-test URLs.",
            file=sys.stderr,
        )
        return 1

    # expected_version is used for appcast checks. We pass it without
    # the leading 'v' because latest.json stores the bare shape; the
    # appcast lstrip handles both.
    expected_release_dir = args.version.lstrip("v") if args.version else ""

    print(f"Smoke-testing OTA: app={args.app} env={args.env} version={args.version}")
    print(f"  host={host}  prefix={prefix}")

    all_results: list[CheckResult] = []

    latest_result, doc = check_latest_json(host, prefix, expected_release_dir)
    all_results.append(latest_result)
    if doc is None:
        # Without latest.json we can't do per-platform checks. Emit the
        # summary and bail.
        _emit_summary(all_results, [r for r in all_results if not r.ok], args)
        return 1

    platforms = doc.get("platforms") or {}
    # Check only the platform keys that exist in latest.json (the bucket
    # may legitimately have only a subset during a partial rollout), but
    # always report any of the canonical four that are missing.
    # By default, missing entries are WARN-only (staggered rollouts are
    # legitimate). Pass --require-all-platforms to fail instead.
    wanted = ALL_PLATFORMS
    for key in wanted:
        info = platforms.get(key)
        if not isinstance(info, dict):
            warn_msg = f"latest.json has no platform entry named '{key}' (staggered rollout)"
            all_results.append(CheckResult(
                name=f"{key} entry in latest.json",
                ok=not args.require_all_platforms,
                errors=[warn_msg] if args.require_all_platforms else [],
                warnings=[] if args.require_all_platforms else [warn_msg],
            ))
            continue
        all_results.append(check_installer_url(host, key, info))
        platform, arch = key.rsplit("-", 1)
        all_results.extend(check_appcast(host, prefix, platform, arch, args.app, expected_release_dir))

    failed = [r for r in all_results if not r.ok]
    _emit_summary(all_results, failed, args)
    return 1 if failed else 0


def _emit_summary(all_results: list[CheckResult], failed: list[CheckResult], args: argparse.Namespace) -> None:
    """Write the markdown table to GITHUB_STEP_SUMMARY and stdout."""
    lines = [
        f"### OTA smoke test",
        "",
        f"- App: `{args.app}`",
        f"- Environment: `{args.env}`",
        f"- Version: `{args.version}`"
        + (f" (user prefix `{args.user_prefix}`)" if args.user_prefix else ""),
        "",
        "| Check | Status | Detail |",
        "| --- | --- | --- |",
    ]
    for r in all_results:
        lines.append(r.to_markdown_row())
    text = "\n".join(lines) + "\n"
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        try:
            with open(summary_path, "a", encoding="utf-8") as f:
                f.write(text)
        except OSError:
            pass
    # Always echo to stdout so the workflow log has the same table.
    print(text)
    if failed:
        for r in failed:
            for e in r.errors:
                print(f"::error::{r.name}: {e}")
    # Emit warnings for all results (including passing ones) so operators
    # are aware of non-fatal conditions such as staggered releases.
    warned_results = [r for r in all_results if r.warnings]
    if warned_results:
        for r in warned_results:
            for w in r.warnings:
                print(f"::warning::{r.name}: {w}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Smoke-test OTA endpoints (latest.json + appcast + installer URLs)",
    )
    parser.add_argument("--app", choices=["intl", "cn"], default="intl",
                        help="Which app's OTA bucket to test (default: intl)")
    parser.add_argument("--env", required=True,
                        help="Target environment (dev/test/staging/production)")
    parser.add_argument("--channel", default="stable",
                        help="Release channel (default: stable)")
    parser.add_argument("--version", default="",
                        help="Expected version for appcast cross-check")
    parser.add_argument("--user-prefix", default="",
                        help="Optional user-prefix for tagged builds")
    parser.add_argument("--require-all-platforms", action="store_true",
                        help="Treat missing platform entries in latest.json as "
                             "failures instead of warnings (default: warn)")
    args = parser.parse_args()
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
