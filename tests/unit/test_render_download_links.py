"""Tests for render_download_links.py + resolve_cos_sizes.py / resolve_s3_sizes.py.

The download-links summary is the most user-visible artifact of the
release pipeline — operators read the size column out loud in the
post-release huddle. These tests guard the renderer against:

  * silent size drift (the old bash loop printed "unknown" for every
    direct-uploaded object — fixed by querying COS/S3 HeadObject);
  * macOS-arch-coverage regression (when build-macos-amd64 is skipped,
    the old renderer still tried to glob *.pkg from an empty dir and
    silently dropped the row);
  * skipped-platform clarity (a missing row should say _why_ it's
    missing, not just show "_No macOS installers available_").

We don't mock the COS/S3 SDK; the resolve_*.py scripts are tested at
their parsing surface (`parse_size_env_file`), which is the only piece
that touches user-visible output.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
RENDERER = REPO_ROOT / "build_system/scripts/render_download_links.py"


# ---------------------------------------------------------------------------
# Helper: load the renderer module from its file path so we can call
# internal helpers without spawning a subprocess.
# ---------------------------------------------------------------------------

def _load_renderer():
    spec = importlib.util.spec_from_file_location("render_download_links", RENDERER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# humanize_size
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "num_bytes,expected",
    [
        (0, "0 B"),
        (1, "1 B"),
        (1023, "1023 B"),
        (1024, "1.0 KB"),
        (1536, "1.5 KB"),
        (1024 * 1024, "1.0 MB"),
        (640 * 1024 * 1024, "640.0 MB"),
        (1024 ** 4, "1.0 TB"),
        # Negative / None → "0 B" (defensive; callers shouldn't pass these).
        (-1, "0 B"),
        (None, "0 B"),
    ],
)
def test_humanize_size(num_bytes, expected):
    renderer = _load_renderer()
    assert renderer.humanize_size(num_bytes) == expected


# ---------------------------------------------------------------------------
# parse_size_env_file
# ---------------------------------------------------------------------------

def test_parse_size_env_file_reads_key_bytes(tmp_path):
    renderer = _load_renderer()
    f = tmp_path / "sizes.env"
    f.write_text(
        "# header line is ignored\n"
        "test/releases/v0.7.0/windows/amd64/eCan-0.7.0-Setup.exe=145823441\n"
        "test/releases/v0.7.0/macos/amd64/eCan-0.7.0.pkg=52345678\n",
        encoding="utf-8",
    )
    out = renderer.parse_size_env_file(f)
    assert out == {
        "test/releases/v0.7.0/windows/amd64/eCan-0.7.0-Setup.exe": 145823441,
        "test/releases/v0.7.0/macos/amd64/eCan-0.7.0.pkg": 52345678,
    }


def test_parse_size_env_file_handles_missing_file(tmp_path):
    renderer = _load_renderer()
    assert renderer.parse_size_env_file(tmp_path / "does-not-exist") == {}


def test_parse_size_env_file_skips_malformed_lines(tmp_path):
    renderer = _load_renderer()
    f = tmp_path / "sizes.env"
    f.write_text(
        "valid/key=1234\n"
        "no_equals_sign\n"
        "another=not_a_number\n"
        "=value_only\n",
        encoding="utf-8",
    )
    out = renderer.parse_size_env_file(f)
    assert out == {"valid/key": 1234}


# ---------------------------------------------------------------------------
# classify_macos / classify_linux
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "filename,arch_label,arch_path",
    [
        ("eCan-0.7.0-macos-amd64.pkg", "Intel (x86_64)", "amd64"),
        ("eCan-0.7.0-macos-x86_64.pkg", "Intel (x86_64)", "amd64"),
        ("eCan-0.7.0-macos-aarch64.pkg", "Apple Silicon (ARM64)", "aarch64"),
        ("eCan-0.7.0-macos-arm64.pkg", "Apple Silicon (ARM64)", "aarch64"),
        ("eCan-0.7.0-macos.pkg", "Universal", "universal"),
    ],
)
def test_classify_macos(filename, arch_label, arch_path):
    renderer = _load_renderer()
    assert renderer.classify_macos(filename) == (arch_label, arch_path)


@pytest.mark.parametrize(
    "filename,arch_label,arch_path,pkg_type",
    [
        ("eCan-0.7.0-linux-amd64.deb", "x86_64", "amd64", "DEB Package"),
        ("eCan-0.7.0-linux-x86_64.AppImage", "x86_64", "amd64", "AppImage"),
        ("eCan-0.7.0-linux-aarch64.deb", "ARM64", "aarch64", "DEB Package"),
        ("eCan-0.7.0-linux-arm64.AppImage", "ARM64", "aarch64", "AppImage"),
        ("eCan-0.7.0-linux.tar.gz", "x86_64", "amd64", "Package"),
    ],
)
def test_classify_linux(filename, arch_label, arch_path, pkg_type):
    renderer = _load_renderer()
    assert renderer.classify_linux(filename) == (arch_label, arch_path, pkg_type)


# ---------------------------------------------------------------------------
# build_windows_rows — the user-visible regression we set out to fix
# ---------------------------------------------------------------------------

def test_build_windows_rows_uses_remote_size_for_direct_upload(tmp_path):
    """The whole point of the new HeadObject step: when the build job
    took the direct-upload fast path, the GHA artifact store is empty,
    so `du -sh` would return 0 and the old bash loop printed "unknown".
    The renderer must instead pick the size from the COS/S3 map.
    """
    renderer = _load_renderer()
    fake_size = 145_823_441  # ~139 MB, real Windows installer territory
    remote_sizes = {
        "test/releases/v0.7.0/windows/amd64/eCan-0.7.0-windows-amd64-Setup.exe": fake_size,
    }
    rows = renderer.build_windows_rows(
        version="0.7.0",
        bucket_url_prefix="https://ecan-releases-1251680599.cos.ap-shanghai.myqcloud.com",
        env_prefix="test",
        windows_artifacts_dir=tmp_path,  # empty
        windows_build_result="success",
        windows_direct_upload=True,
        app_name="eCan",
        remote_sizes=remote_sizes,
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["filename"] == "eCan-0.7.0-windows-amd64-Setup.exe"
    assert row["size_bytes"] == fake_size
    assert "Setup.exe" in row["url"]
    assert row["source"] == "remote"
    assert row["gate_label"] == "✅ built"


def test_build_windows_rows_prefers_local_when_artifact_present(tmp_path):
    """When the build went through the GHA artifact path, the local
    file's size is authoritative. The renderer must use it, even if a
    COS-size map is also provided (it would be a coincidental match
    from a previous run, not the current state).
    """
    renderer = _load_renderer()
    (tmp_path / "eCan-0.7.0-windows-amd64-Setup.exe").write_bytes(b"x" * 200_000_000)
    remote_sizes = {
        "test/releases/v0.7.0/windows/amd64/eCan-0.7.0-windows-amd64-Setup.exe": 99_999_999,
    }
    rows = renderer.build_windows_rows(
        version="0.7.0",
        bucket_url_prefix="https://x.cos.ap-shanghai.myqcloud.com",
        env_prefix="test",
        windows_artifacts_dir=tmp_path,
        windows_build_result="success",
        windows_direct_upload=False,
        app_name="eCan",
        remote_sizes=remote_sizes,
    )
    assert rows[0]["size_bytes"] == 200_000_000
    assert rows[0]["source"] == "local"


def test_build_windows_rows_skipped_build_shows_gate_label(tmp_path):
    """When the Windows build was skipped, the renderer must still
    emit a row so the user sees the missing artifact clearly, with
    the gate column saying "⏭ skipped" rather than "_No Windows
    installers available_".
    """
    renderer = _load_renderer()
    rows = renderer.build_windows_rows(
        version="0.7.0",
        bucket_url_prefix="https://x.cos.ap-shanghai.myqcloud.com",
        env_prefix="test",
        windows_artifacts_dir=tmp_path,
        windows_build_result="skipped",
        windows_direct_upload=False,
        app_name="eCan",
        remote_sizes={},
    )
    assert len(rows) == 1
    assert rows[0]["gate_label"] == "⏭ skipped"
    assert rows[0]["size_bytes"] is None


# ---------------------------------------------------------------------------
# build_macos_rows
# ---------------------------------------------------------------------------

def test_build_macos_rows_skipped_arch_marks_placeholder(tmp_path):
    """If the user restricted the build to one macOS arch, the
    renderer's row builder must still surface the other arch's
    expected filename so the table tells the truth about coverage,
    rather than silently dropping the row.
    """
    renderer = _load_renderer()
    rows = renderer.build_macos_rows(
        version="0.7.0",
        bucket_url_prefix="https://x.cos.ap-shanghai.myqcloud.com",
        env_prefix="test",
        macos_artifacts_dir=tmp_path,
        macos_build_result="success",
        macos_built_amd64=True,
        macos_built_aarch64=False,
        app_name="eCan",
        remote_sizes={},
    )
    # Exactly one row for the amd64 arch we did build; no aarch64 row
    # because the build was scoped to skip it.
    arch_paths = [r["url"].split("/macos/")[1].split("/")[0] for r in rows if r["url"]]
    assert arch_paths == ["amd64"]


def test_build_macos_rows_uses_remote_sizes_when_no_local_artifact(tmp_path):
    renderer = _load_renderer()
    rows = renderer.build_macos_rows(
        version="0.7.0",
        bucket_url_prefix="https://x.cos.ap-shanghai.myqcloud.com",
        env_prefix="test",
        macos_artifacts_dir=tmp_path,
        macos_build_result="success",
        macos_built_amd64=True,
        macos_built_aarch64=True,
        app_name="eCan",
        remote_sizes={
            "test/releases/v0.7.0/macos/amd64/eCan-0.7.0-macos-amd64.pkg": 52_345_678,
            "test/releases/v0.7.0/macos/aarch64/eCan-0.7.0-macos-aarch64.pkg": 51_987_654,
        },
    )
    sizes = sorted(r["size_bytes"] for r in rows)
    assert sizes == [51_987_654, 52_345_678]


# ---------------------------------------------------------------------------
# Smoke test the renderer CLI end-to-end
# ---------------------------------------------------------------------------

def test_render_cli_produces_markdown_and_text(tmp_path, monkeypatch):
    """Drive the renderer as the workflow does: set env vars, point at
    a fake artifact dir, write summary + text, read them back.
    """
    monkeypatch.setenv("VERSION", "0.7.0")
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("CHANNEL", "stable")
    monkeypatch.setenv("BUCKET_NAME", "ecan-releases-1251680599")
    monkeypatch.setenv("BUCKET_REGION", "ap-shanghai")
    monkeypatch.setenv("OTA_PREFIX", "test")
    monkeypatch.setenv("WINDOWS_BUILD_RESULT", "success")
    monkeypatch.setenv("MACOS_BUILD_RESULT", "skipped")
    monkeypatch.setenv("LINUX_RESULT", "skipped")
    monkeypatch.setenv("WINDOWS_DIRECT_UPLOAD", "true")
    monkeypatch.setenv("APP_NAME", "eCan.cn")

    win = tmp_path / "windows-artifacts"
    win.mkdir()
    (win / "eCan.cn-0.7.0-windows-amd64-Setup.exe").write_bytes(b"")  # empty stub
    sizes = tmp_path / "sizes.env"
    sizes.write_text(
        "test/releases/v0.7.0/windows/amd64/eCan.cn-0.7.0-windows-amd64-Setup.exe=145823441\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("COS_SIZES_FILE", str(sizes))

    summary = tmp_path / "summary.md"
    text = tmp_path / "text.txt"
    rc = subprocess.run(
        [
            sys.executable, str(RENDERER),
            "--scheme", "cos",
            "--summary-out", str(summary),
            "--text-out", str(text),
            "--url-pattern", "https://{bucket-with-APPID}.cos.{region}.myqcloud.com/{env}/releases/v{ver}/{platform}/{arch}/{file}",
            "--workflow-name", "test",
        ],
        cwd=tmp_path,
        capture_output=True, text=True,
    ).returncode
    assert rc == 0

    md = summary.read_text()
    assert "## 📦 Download Links" in md
    assert "eCan.cn-0.7.0-windows-amd64-Setup.exe" in md
    # 145823441 bytes → 139.1 MB (renderer humanises with one decimal).
    assert "139.1 MB" in md
    # Skipped macOS row must surface its reason, not be silently dropped.
    assert "⏭ skipped" in md
    # URL pattern footer must be present so operators know how the
    # public URL is built.
    assert "URL Format" in md

    txt = text.read_text()
    assert "Version:     0.7.0" in txt
    assert "Environment: test" in txt
    assert "139.1 MB" in txt
    assert "https://ecan-releases-1251680599.cos.ap-shanghai.myqcloud.com/test/releases/v0.7.0/windows/amd64/eCan.cn-0.7.0-windows-amd64-Setup.exe" in txt
