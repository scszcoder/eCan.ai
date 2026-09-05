"""Render the Download Links summary + text artifact.

Used by `.github/workflows/shared-{cos,s3}-download-links.yml`. Single
script so the CN (COS) and Intl (S3) summaries stay byte-identical in
layout, even though the size-resolution backend differs.

Inputs (env vars):
    VERSION                  release version, e.g. 0.7.0-lq_dev_multi-ca3fb6c
    ENVIRONMENT              development / test / staging / production
    CHANNEL                  dev / beta / stable
    BUCKET_NAME              bucket name (with APPID for COS, plain name for S3)
    BUCKET_REGION            e.g. ap-shanghai / us-east-1
    OTA_PREFIX               env-level prefix (dev/test/staging/production/…)
    USER_PREFIX              optional lowercase per-user prefix (e.g. 'songc');
                            when set, URLs target `<prefix>_v<version>/...`
                            to match where `upload_to_*.py` actually wrote.
                            Empty for normal semver / branch builds.
    BASE_URL                 public URL prefix, e.g. https://ecan-….myqcloud.com
                            or https://ecan-releases.s3.us-east-1.amazonaws.com.
                            If unset, computed from BUCKET_NAME + BUCKET_REGION.
    WINDOWS_BUILD_RESULT     success / skipped / failure
    MACOS_BUILD_RESULT       success / skipped / failure
    LINUX_RESULT             success / skipped / failure
    APP_NAME                 installer prefix; default "eCan"
    WINDOWS_DIRECT_UPLOAD    "true" / "false" — when true, the GHA artifact
                            path is unavailable and we read sizes from COS/S3.

Optional inputs for size resolution:
    COS_SIZES_FILE           path to a file produced by resolve_cos_sizes.py,
                            one line per object: `<key>=<bytes>`. Used to fill
                            sizes for direct-uploaded objects without re-doing
                            the HeadObject calls here.
    S3_SIZES_FILE            same, for the S3 variant.

Paths the script inspects (relative to CWD):
    windows-artifacts/, macos-amd64-artifacts/, macos-aarch64-artifacts/,
    macos-artifacts/ (merged), linux-artifacts/

Outputs:
    --summary-out <path>     Markdown written to GITHUB_STEP_SUMMARY
    --text-out    <path>     Text artifact uploaded as workflow artifact

Exit codes:
    0  always (best-effort render; the workflow job must not fail on
       summary glitches).
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Size helpers
# ---------------------------------------------------------------------------

# Matches "<prefix>_v<version>" where prefix is 1-32 chars starting with
# a letter. Same shape as `upload_to_s3.py::S3Uploader.release_dir` and
# the on-bucket convention documented in ota/docs/multi_version_picker.md
# — kept in sync so the render side never picks a different directory
# than the upload side wrote to.
_PREFIXED_DIR_RE = re.compile(r"^([A-Za-z][A-Za-z0-9]{0,31})_v(\d.*)$")


def release_dir_for(version: str, user_prefix: str = "") -> str:
    """Return the on-bucket directory name for this release.

    Mirrors `build_system/scripts/generate_appcast.py::_to_release_dir`
    (and, transitively, the write-side logic in upload_to_s3.py /
    upload_to_cos.py) so the rendered URLs and the keys the resolve_*.py
    scripts probe match where the upload script actually wrote.

    `version` is expected to be the bare ``X.Y.Z[-suffix]`` shape coming
    out of validate-tag (no leading 'v' and no user-prefix segment).
    When `version` is already in directory form (``v1.0.0`` or
    ``songc_v1.0.0``), it is returned verbatim — same idempotency as
    the appcast helper, so re-feeding the dir form back through this
    function can't drift.
    """
    if not version:
        return version
    user_prefix = (user_prefix or "").strip().lower()
    if version.startswith("v") or _PREFIXED_DIR_RE.match(version):
        return version
    if user_prefix:
        return f"{user_prefix}_v{version}"
    return f"v{version}"


def humanize_size(num_bytes: int) -> str:
    """Render a byte count as a human-readable string.

    Mirrors `du -sh`'s "K/M/G" rounding but always reports a positive value
    so empty / stub files don't show up as "0". Used both for live (downloaded)
    files and for sizes resolved from COS/S3.
    """
    if num_bytes is None or num_bytes <= 0:
        return "0 B"
    units = ("B", "KB", "MB", "GB", "TB")
    size = float(num_bytes)
    for unit in units:
        if size < 1024.0 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"  # pragma: no cover


def parse_size_env_file(path: Path) -> dict[str, int]:
    """Parse a `key=bytes` env-style file (resolve_cos_sizes.py output).

    Lines look like:
        test/releases/v0.7.0/windows/amd64/eCan-...-Setup.exe=145823441
    Returns {key: int_bytes}. Missing or malformed lines are skipped.
    """
    sizes: dict[str, int] = {}
    if not path or not path.exists():
        return sizes
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        try:
            sizes[key] = int(value.strip())
        except ValueError:
            continue
    return sizes


# ---------------------------------------------------------------------------
# Arch / type classification
# ---------------------------------------------------------------------------

def classify_macos(filename: str) -> tuple[str, str]:
    """Return (arch_label, arch_path) for a macOS artifact filename."""
    if "amd64" in filename or "x86_64" in filename:
        return "Intel (x86_64)", "amd64"
    if "aarch64" in filename or "arm64" in filename:
        return "Apple Silicon (ARM64)", "aarch64"
    return "Universal", "universal"


def classify_linux(filename: str) -> tuple[str, str, str]:
    """Return (arch_label, arch_path, pkg_type) for a Linux artifact filename."""
    if "aarch64" in filename or "arm64" in filename:
        arch_label, arch_path = "ARM64", "aarch64"
    else:
        arch_label, arch_path = "x86_64", "amd64"
    if filename.endswith(".AppImage"):
        pkg_type = "AppImage"
    elif filename.endswith(".deb"):
        pkg_type = "DEB Package"
    else:
        pkg_type = "Package"
    return arch_label, arch_path, pkg_type


# ---------------------------------------------------------------------------
# Artifact discovery
# ---------------------------------------------------------------------------

def discover_files(directory: Path, suffixes: tuple[str, ...]) -> list[Path]:
    """Return files in *directory* matching any suffix, sorted for stability."""
    if not directory.is_dir():
        return []
    out: list[Path] = []
    for suffix in suffixes:
        out.extend(sorted(directory.glob(f"*{suffix}")))
    # De-dup while keeping order.
    return list(dict.fromkeys(out))


def size_for(local_path: Path | None, cos_key: str | None, remote_sizes: dict[str, int]) -> tuple[int | None, str]:
    """Return (size_bytes, source) for a single artifact.

    source is one of: "local", "remote", "missing".
    Prefer the live local file when present (authoritative when build job
    did not direct-upload). Otherwise consult `remote_sizes` keyed by the
    full COS/S3 object key.
    """
    if local_path is not None and local_path.is_file() and local_path.stat().st_size > 0:
        return local_path.stat().st_size, "local"
    if cos_key and cos_key in remote_sizes:
        return remote_sizes[cos_key], "remote"
    return None, "missing"


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

# Per-platform gate text shown in the "missing" rows so it's obvious why
# a row is empty (build skipped vs. failure is in WINDOWS_BUILD_RESULT etc).
_BUILD_RESULT_LABELS = {
    "success": "✅ built",
    "skipped": "⏭ skipped",
    "failure": "❌ failed",
    "cancelled": "🚫 cancelled",
}


def _format_size_cell(size_bytes: int | None) -> str:
    if size_bytes is None:
        return "_(missing — check bucket)_"
    return humanize_size(size_bytes)


def render_windows_table(rows: list[dict]) -> list[str]:
    """Render the Windows section as a Markdown table.

    `rows` is a list of dicts with keys:
        filename, arch_label, size_bytes, source, url, gate_label
    """
    if not rows:
        return [
            "### Windows Installers (x86_64)",
            "",
            "_No Windows installers available for this release._",
            "",
        ]
    lines = ["### Windows Installers (x86_64)", ""]
    lines.append("| File | Arch | Size | Build | URL |")
    lines.append("| --- | --- | ---: | --- | --- |")
    for row in rows:
        lines.append(
            f"| `{row['filename']}` "
            f"| {row['arch_label']} "
            f"| {_format_size_cell(row['size_bytes'])} "
            f"| {row['gate_label']} "
            f"| [Download]({row['url']}) |"
        )
    lines.append("")
    return lines


def render_macos_table(rows: list[dict]) -> list[str]:
    if not rows:
        return [
            "### macOS Installers",
            "",
            "_No macOS installers available for this release._",
            "",
        ]
    lines = ["### macOS Installers", ""]
    lines.append("| File | Arch | Size | Build | URL |")
    lines.append("| --- | --- | ---: | --- | --- |")
    for row in rows:
        lines.append(
            f"| `{row['filename']}` "
            f"| {row['arch_label']} "
            f"| {_format_size_cell(row['size_bytes'])} "
            f"| {row['gate_label']} "
            f"| [Download]({row['url']}) |"
        )
    lines.append("")
    return lines


def render_linux_table(rows: list[dict]) -> list[str]:
    if not rows:
        return [
            "### Linux Packages",
            "",
            "_No Linux packages available for this release._",
            "",
        ]
    lines = ["### Linux Packages", ""]
    lines.append("| File | Type | Arch | Size | Build | URL |")
    lines.append("| --- | --- | --- | ---: | --- | --- |")
    for row in rows:
        lines.append(
            f"| `{row['filename']}` "
            f"| {row['pkg_type']} "
            f"| {row['arch_label']} "
            f"| {_format_size_cell(row['size_bytes'])} "
            f"| {row['gate_label']} "
            f"| [Download]({row['url']}) |"
        )
    lines.append("")
    return lines


def render_header(meta: dict) -> list[str]:
    """Render the summary header (title + version/env/channel)."""
    return [
        "## 📦 Download Links",
        "",
        f"- **Version**: `{meta['version']}`",
        f"- **Environment**: `{meta['environment']}`",
        f"- **Channel**: `{meta['channel']}`",
        f"- **Bucket**: `{meta['bucket']}` (region `{meta['region']}`)",
        "",
    ]


def render_footer(url_pattern: str) -> list[str]:
    return [
        "---",
        "",
        "### 📝 URL Format",
        "",
        f"- Pattern: `{url_pattern}`",
        "- Size column is read from the GHA artifact when the build job uploaded",
        "  through `actions/upload-artifact`, and queried via `HeadObject` on the",
        "  storage backend when the build job took the direct-upload fast path.",
        "",
    ]


# ---------------------------------------------------------------------------
# Per-row construction
# ---------------------------------------------------------------------------

def build_windows_rows(
    *,
    version: str,
    release_dir: str,
    bucket_url_prefix: str,
    env_prefix: str,
    windows_artifacts_dir: Path,
    windows_build_result: str,
    windows_direct_upload: bool,
    app_name: str,
    remote_sizes: dict[str, int],
) -> list[dict]:
    """Build the rows for the Windows table.

    When the build job direct-uploaded, `windows-artifacts/` is empty (the
    "Synthesize" step creates a zero-byte stub). The loop therefore
    synthesises one row from version + app-name, and resolves its size
    via the remote-sizes map.

    When the build job went through the GHA artifact path, we iterate the
    downloaded files and prefer their on-disk size.
    """
    rows: list[dict] = []
    gate_label = _BUILD_RESULT_LABELS.get(windows_build_result, windows_build_result)

    if windows_build_result != "success":
        return [{
            "filename": f"{app_name}-{version}-windows-amd64-Setup.exe",
            "arch_label": "x86_64",
            "size_bytes": None,
            "url": f"{bucket_url_prefix}/{env_prefix}/releases/{release_dir}/windows/amd64/{app_name}-{version}-windows-amd64-Setup.exe",
            "gate_label": gate_label,
            "source": "missing",
        }]

    candidates: list[Path] = []
    if windows_direct_upload:
        # Synthesize the expected installer filename so the row exists even
        # though the GHA artifact wasn't downloaded.
        candidates = [Path(f"{app_name}-{version}-windows-amd64-Setup.exe")]
        base_dir = windows_artifacts_dir  # may or may not contain the stub
        local_paths = {p.name: p for p in discover_files(windows_artifacts_dir, (".exe", ".msi"))}
    else:
        local_paths = {p.name: p for p in discover_files(windows_artifacts_dir, (".exe", ".msi"))}
        candidates = list(local_paths.values())
        base_dir = None

    for path in candidates:
        filename = path.name if isinstance(path, Path) else str(path)
        local_path = local_paths.get(filename) if local_paths else None
        key = f"{env_prefix}/releases/{release_dir}/windows/amd64/{filename}"
        size, source = size_for(local_path, key, remote_sizes)
        rows.append({
            "filename": filename,
            "arch_label": "x86_64",
            "size_bytes": size,
            "url": f"{bucket_url_prefix}/{key}",
            "gate_label": gate_label,
            "source": source,
        })
    return rows


def build_macos_rows(
    *,
    version: str,
    release_dir: str,
    bucket_url_prefix: str,
    env_prefix: str,
    macos_artifacts_dir: Path,
    macos_build_result: str,
    macos_built_amd64: bool,
    macos_built_aarch64: bool,
    app_name: str,
    remote_sizes: dict[str, int],
) -> list[dict]:
    rows: list[dict] = []
    gate_label = _BUILD_RESULT_LABELS.get(macos_build_result, macos_build_result)

    # Empty-state placeholder when nothing was built.
    if macos_build_result != "success":
        rows.append({
            "filename": "(no macOS artifact)",
            "arch_label": "—",
            "size_bytes": None,
            "url": "",
            "gate_label": gate_label,
            "source": "missing",
        })
        return rows

    found_files = discover_files(macos_artifacts_dir, (".pkg", ".zip", ".dmg"))
    local_paths = {p.name: p for p in found_files}

    # If the build was scoped to only one arch, make sure the other arch
    # gets a "(not built this run)" placeholder so the table tells the
    # truth about coverage.
    expected: list[tuple[str, str]] = []
    if macos_built_amd64:
        expected.append(("amd64", f"{app_name}-{version}-macos-amd64.pkg"))
    if macos_built_aarch64:
        expected.append(("aarch64", f"{app_name}-{version}-macos-aarch64.pkg"))
    # Always include any discovered files (e.g. .zip bundles) that aren't
    # in the expected list, so we don't silently drop real artifacts.
    discovered_names = {p.name for p in found_files}
    for arch_path, expected_name in expected:
        if expected_name in discovered_names:
            continue
        # Allow common naming variants the build script might emit.
        matches = [
            n for n in discovered_names
            if arch_path in n and (n.endswith(".pkg") or n.endswith(".zip") or n.endswith(".dmg"))
        ]
        for m in matches:
            expected.append((arch_path, m))
            discovered_names.discard(m)

    seen: set[str] = set()
    for arch_path, filename in expected:
        if filename in seen:
            continue
        seen.add(filename)
        local_path = local_paths.get(filename)
        key = f"{env_prefix}/releases/{release_dir}/macos/{arch_path}/{filename}"
        size, source = size_for(local_path, key, remote_sizes)
        arch_label, _ = classify_macos(filename)
        rows.append({
            "filename": filename,
            "arch_label": arch_label,
            "size_bytes": size,
            "url": f"{bucket_url_prefix}/{key}",
            "gate_label": gate_label,
            "source": source,
        })

    if not rows:
        rows.append({
            "filename": "(no macOS artifact)",
            "arch_label": "—",
            "size_bytes": None,
            "url": "",
            "gate_label": gate_label,
            "source": "missing",
        })
    return rows


def build_linux_rows(
    *,
    version: str,
    release_dir: str,
    bucket_url_prefix: str,
    env_prefix: str,
    linux_artifacts_dir: Path,
    linux_result: str,
    app_name: str,
    remote_sizes: dict[str, int],
) -> list[dict]:
    rows: list[dict] = []
    gate_label = _BUILD_RESULT_LABELS.get(linux_result, linux_result)

    if linux_result != "success":
        return [{
            "filename": f"{app_name}-{version}-linux-amd64.deb",
            "arch_label": "x86_64",
            "pkg_type": "DEB Package",
            "size_bytes": None,
            "url": f"{bucket_url_prefix}/{env_prefix}/releases/{release_dir}/linux/amd64/{app_name}-{version}-linux-amd64.deb",
            "gate_label": gate_label,
            "source": "missing",
        }]

    local_paths = {p.name: p for p in discover_files(linux_artifacts_dir, (".AppImage", ".deb", ".rpm", ".tar.gz"))}
    for filename, local_path in local_paths.items():
        arch_label, arch_path, pkg_type = classify_linux(filename)
        key = f"{env_prefix}/releases/{release_dir}/linux/{arch_path}/{filename}"
        size, source = size_for(local_path, key, remote_sizes)
        rows.append({
            "filename": filename,
            "arch_label": arch_label,
            "pkg_type": pkg_type,
            "size_bytes": size,
            "url": f"{bucket_url_prefix}/{key}",
            "gate_label": gate_label,
            "source": source,
        })
    return rows


# ---------------------------------------------------------------------------
# Text artifact
# ---------------------------------------------------------------------------

def _format_size_text(size_bytes: int | None) -> str:
    if size_bytes is None:
        return "missing (check bucket)"
    return humanize_size(size_bytes)


def _format_extra_field(field: str) -> tuple[str, str]:
    """Map a row key to its (label, max_width) pair for the text artifact."""
    mapping = {
        "arch_label": ("Arch", "Arch:"),
        "pkg_type": ("Type", "Type:"),
    }
    return mapping.get(field, (field.replace("_", " ").capitalize(), field))


def render_text(
    meta: dict,
    windows_rows: list[dict],
    macos_rows: list[dict],
    linux_rows: list[dict],
) -> str:
    lines = [
        f"{meta['app_name']} Download Links",
        "",
        f"Version:     {meta['version']}",
        f"Environment: {meta['environment']}",
        f"Channel:     {meta['channel']}",
        f"Bucket:      {meta['bucket']} ({meta['region']})",
        f"Generated:   {meta['generated_at']}",
        "",
    ]

    def emit_section(title: str, rows: list[dict], extra_fields: tuple[str, ...] = ()) -> None:
        lines.append(f"[{title}]")
        lines.append("")
        if not rows or all(r.get("source") == "missing" for r in rows):
            lines.append(f"  (no {title.lower()} artifacts in this release)")
            lines.append("")
            return
        for r in rows:
            if r.get("source") == "missing":
                continue
            lines.append(f"  {r['filename']}")
            for field in extra_fields:
                value = r.get(field)
                if value:
                    label, _ = _format_extra_field(field)
                    lines.append(f"    {label:<10} {value}")
            lines.append(f"    Size:      {_format_size_text(r['size_bytes'])}")
            lines.append(f"    Build:     {r['gate_label']}")
            lines.append(f"    URL:       {r['url']}")
            lines.append("")

    emit_section("Windows", windows_rows)
    emit_section("macOS", macos_rows, extra_fields=("arch_label",))
    emit_section("Linux", linux_rows, extra_fields=("pkg_type", "arch_label"))

    lines.append("---")
    lines.append(f"Generated by {meta['workflow']} at {meta['generated_at']}")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _resolve_base_url(bucket: str, region: str, override: str, scheme: str) -> str:
    """Build the public URL prefix for the bucket.

    `scheme` is "cos" for CN (Tencent Cloud) or "s3" for Intl (AWS).
    Falls back to the historical URL patterns when BUCKET_NAME / REGION are
    not present in env (e.g. dry-run).
    """
    if override:
        return override.rstrip("/")
    if not bucket or not region:
        return ""
    if scheme == "cos":
        return f"https://{bucket}.cos.{region}.myqcloud.com"
    if scheme == "s3":
        return f"https://{bucket}.s3.{region}.amazonaws.com"
    return f"https://{bucket}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--scheme", choices=("cos", "s3"), required=True,
                        help="Storage backend. Determines URL pattern only; "
                             "size resolution is driven by the *_SIZES_FILE env.")
    parser.add_argument("--summary-out", required=True,
                        help="Path to write the Markdown summary to.")
    parser.add_argument("--text-out", required=True,
                        help="Path to write the text artifact to.")
    parser.add_argument("--url-pattern", required=True,
                        help="Pattern string shown in the summary footer.")
    parser.add_argument("--workflow-name", required=True,
                        help="Name of the workflow emitting this summary "
                             "(recorded in the text artifact header).")
    args = parser.parse_args()

    version = os.environ.get("VERSION", "")
    environment = os.environ.get("ENVIRONMENT", "")
    channel = os.environ.get("CHANNEL", "")
    bucket = os.environ.get("BUCKET_NAME", "")
    region = os.environ.get("BUCKET_REGION", "")
    env_prefix = os.environ.get("OTA_PREFIX") or environment
    base_url_override = os.environ.get("BASE_URL", "")
    base_url = _resolve_base_url(bucket, region, base_url_override, args.scheme)
    user_prefix = os.environ.get("USER_PREFIX", "")
    release_dir = release_dir_for(version, user_prefix)

    windows_build_result = os.environ.get("WINDOWS_BUILD_RESULT", "skipped")
    macos_build_result = os.environ.get("MACOS_BUILD_RESULT", "skipped")
    linux_result = os.environ.get("LINUX_RESULT", "skipped")
    windows_direct_upload = os.environ.get("WINDOWS_DIRECT_UPLOAD", "false").lower() == "true"
    app_name = os.environ.get("APP_NAME", "eCan")
    macos_built_amd64 = os.environ.get("MACOS_BUILT_AMD64", "true").lower() != "false"
    macos_built_aarch64 = os.environ.get("MACOS_BUILT_AARCH64", "true").lower() != "false"

    remote_sizes: dict[str, int] = {}
    sizes_env_file = (
        os.environ.get("COS_SIZES_FILE") if args.scheme == "cos"
        else os.environ.get("S3_SIZES_FILE")
    )
    if sizes_env_file:
        remote_sizes = parse_size_env_file(Path(sizes_env_file))

    windows_rows = build_windows_rows(
        version=version,
        release_dir=release_dir,
        bucket_url_prefix=base_url,
        env_prefix=env_prefix,
        windows_artifacts_dir=Path("windows-artifacts"),
        windows_build_result=windows_build_result,
        windows_direct_upload=windows_direct_upload,
        app_name=app_name,
        remote_sizes=remote_sizes,
    )
    macos_rows = build_macos_rows(
        version=version,
        release_dir=release_dir,
        bucket_url_prefix=base_url,
        env_prefix=env_prefix,
        macos_artifacts_dir=Path("macos-artifacts"),
        macos_build_result=macos_build_result,
        macos_built_amd64=macos_built_amd64,
        macos_built_aarch64=macos_built_aarch64,
        app_name=app_name,
        remote_sizes=remote_sizes,
    )
    linux_rows = build_linux_rows(
        version=version,
        release_dir=release_dir,
        bucket_url_prefix=base_url,
        env_prefix=env_prefix,
        linux_artifacts_dir=Path("linux-artifacts"),
        linux_result=linux_result,
        app_name=app_name,
        remote_sizes=remote_sizes,
    )

    meta = {
        "version": version,
        "environment": environment,
        "channel": channel,
        "bucket": bucket,
        "region": region,
        "app_name": app_name,
        "workflow": args.workflow_name,
        "generated_at": "$(date -u +\"%Y-%m-%dT%H:%M:%SZ\")",  # expanded by shell below
    }
    # Replace the placeholder with a real timestamp at write time so we
    # don't depend on Python's strftime timezone config.
    import subprocess
    ts = subprocess.run(
        ["date", "-u", "+%Y-%m-%dT%H:%M:%SZ"],
        capture_output=True, text=True, check=False,
    ).stdout.strip() or "unknown"
    meta["generated_at"] = ts

    summary_lines: list[str] = []
    summary_lines.extend(render_header(meta))
    summary_lines.extend(render_windows_table(windows_rows))
    summary_lines.extend(render_macos_table(macos_rows))
    summary_lines.extend(render_linux_table(linux_rows))
    summary_lines.extend(render_footer(args.url_pattern))

    Path(args.summary_out).write_text("\n".join(summary_lines), encoding="utf-8")
    Path(args.text_out).write_text(
        render_text(meta, windows_rows, macos_rows, linux_rows),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
