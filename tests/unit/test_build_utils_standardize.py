"""
Regression tests for build_system/build_utils.standardize_artifact_names
and the platform-specific helpers it dispatches to.

The previous cn artifact-naming drift (the bug fix landed in commit
64626d44) was caught by a workflow regex, not by any test. These tests
pin the rename behaviour so that a future regression (typo in expected
name, dropped .sig handling, broken duplicate-removal) surfaces here,
not in production.

We call the private helpers directly (monkeypatching platform.system()
to test the other platforms is fragile). Each test creates an isolated
``dist/`` directory under tmp_path, drops fake artifacts in it, and
asserts the post-state.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# build_utils.py is package-style (build_system.build_utils). Add
# the repo root so `import build_system` resolves.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from build_system import build_utils as bu  # noqa: E402


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def dist_dir(tmp_path, monkeypatch):
    """
    Create an empty dist/ under tmp_path and chdir into tmp_path so the
    module-level `Path("dist")` lookups resolve there.
    """
    (tmp_path / "dist").mkdir()
    monkeypatch.chdir(tmp_path)
    return tmp_path / "dist"


# ============================================================================
# Windows
# ============================================================================


class TestWindowsStandardize:
    def test_renames_setup_to_standardized_name(self, dist_dir):
        # Inno Setup output name pattern: "eCan Setup 1.0.0.exe"
        src = dist_dir / "eCan Setup 1.0.0.exe"
        src.write_bytes(b"fake installer")
        bu._standardize_windows_artifacts("1.0.0", "amd64", "eCan")
        assert (dist_dir / "eCan-1.0.0-windows-amd64-Setup.exe").exists()

    def test_renames_app_exe_to_standardized_name(self, dist_dir):
        src = dist_dir / "eCan.exe"
        src.write_bytes(b"fake exe")
        bu._standardize_windows_artifacts("1.0.0", "amd64", "eCan")
        assert (dist_dir / "eCan-1.0.0-windows-amd64.exe").exists()

    def test_app_short_name_overrides_default(self, dist_dir):
        # CN app uses "eCan.cn" as app_short_name.
        src = dist_dir / "eCan.cn.exe"
        src.write_bytes(b"cn exe")
        bu._standardize_windows_artifacts("1.0.0", "amd64", "eCan.cn")
        assert (dist_dir / "eCan.cn-1.0.0-windows-amd64.exe").exists()

    def test_setup_signature_is_renamed_in_sync(self, dist_dir):
        # The OTA signature is generated BEFORE standardize runs. The
        # signature must follow the rename — otherwise upload_to_cos
        # can't find it under the expected name.
        src = dist_dir / "eCan Setup 1.0.0.exe"
        sig = dist_dir / "eCan Setup 1.0.0.exe.sig"
        src.write_bytes(b"installer")
        sig.write_bytes(b"signature")

        bu._standardize_windows_artifacts("1.0.0", "amd64", "eCan")

        assert (dist_dir / "eCan-1.0.0-windows-amd64-Setup.exe").exists()
        assert (dist_dir / "eCan-1.0.0-windows-amd64-Setup.exe.sig").exists()
        # Old sig must be gone.
        assert not sig.exists()

    def test_duplicate_setup_is_removed(self, dist_dir):
        # If both the raw setup AND the standardized name exist
        # (e.g. second pass), the duplicate must be removed.
        primary = dist_dir / "eCan Setup 1.0.0.exe"
        primary.write_bytes(b"installer")
        already = dist_dir / "eCan-1.0.0-windows-amd64-Setup.exe"
        already.write_bytes(b"already here")

        bu._standardize_windows_artifacts("1.0.0", "amd64", "eCan")

        assert already.exists()
        assert not primary.exists()

    def test_aarch64_arch_is_supported(self, dist_dir):
        # Although the macOS aarch64 path is the real one, Windows
        # standardize should accept an aarch64 arg without crashing
        # if it ever ships.
        src = dist_dir / "eCan.exe"
        src.write_bytes(b"exe")
        bu._standardize_windows_artifacts("1.0.0", "aarch64", "eCan")
        assert (dist_dir / "eCan-1.0.0-windows-aarch64.exe").exists()


# ============================================================================
# macOS
# ============================================================================


class TestMacosStandardize:
    def test_renames_pkg_to_standardized_name(self, dist_dir):
        # PyInstaller / pkgbuild emits "eCan-1.0.0.pkg" or
        # "eCan-1.0.0-macos-x86_64.pkg". The helper should land on
        # "eCan-{version}-macos-{arch}.pkg".
        src = dist_dir / "eCan-1.0.0.pkg"
        src.write_bytes(b"fake pkg")
        bu._standardize_macos_artifacts("1.0.0", "amd64", "eCan")
        assert (dist_dir / "eCan-1.0.0-macos-amd64.pkg").exists()

    def test_app_short_name_overrides_default(self, dist_dir):
        src = dist_dir / "eCan.cn-1.0.0.pkg"
        src.write_bytes(b"cn pkg")
        bu._standardize_macos_artifacts("1.0.0", "amd64", "eCan.cn")
        assert (dist_dir / "eCan.cn-1.0.0-macos-amd64.pkg").exists()

    def test_extra_pkgs_are_removed(self, dist_dir):
        # If the build emits multiple .pkg artifacts (shouldn't
        # happen, but defensive), keep the first and remove the rest.
        first = dist_dir / "eCan-1.0.0.pkg"
        first.write_bytes(b"first")
        extra = dist_dir / "eCan-1.0.0-arm64.pkg"
        extra.write_bytes(b"extra")

        bu._standardize_macos_artifacts("1.0.0", "amd64", "eCan")

        assert (dist_dir / "eCan-1.0.0-macos-amd64.pkg").exists()
        assert not extra.exists()

    def test_no_pkg_is_non_fatal(self, dist_dir):
        # Build failed to produce a PKG — must not crash.
        bu._standardize_macos_artifacts("1.0.0", "amd64", "eCan")
        # Nothing to assert beyond "didn't raise".
        assert not list(dist_dir.glob("*.pkg"))


# ============================================================================
# Linux
# ============================================================================


class TestLinuxStandardize:
    def test_renames_deb_to_standardized_name(self, dist_dir):
        src = dist_dir / "eCan_1.0.0_amd64.deb"
        src.write_bytes(b"deb")
        bu._standardize_linux_artifacts("1.0.0", "amd64", "eCan")
        assert (dist_dir / "eCan-1.0.0-linux-amd64.deb").exists()

    def test_renames_appimage_to_standardized_name(self, dist_dir):
        src = dist_dir / "eCan-1.0.0-x86_64.AppImage"
        src.write_bytes(b"appimage")
        bu._standardize_linux_artifacts("1.0.0", "amd64", "eCan")
        assert (dist_dir / "eCan-1.0.0-linux-amd64.AppImage").exists()

    def test_deb_signature_is_renamed_in_sync(self, dist_dir):
        src = dist_dir / "eCan_1.0.0_amd64.deb"
        sig = dist_dir / "eCan_1.0.0_amd64.deb.sig"
        src.write_bytes(b"deb")
        sig.write_bytes(b"signature")

        bu._standardize_linux_artifacts("1.0.0", "amd64", "eCan")

        assert (dist_dir / "eCan-1.0.0-linux-amd64.deb").exists()
        assert (dist_dir / "eCan-1.0.0-linux-amd64.deb.sig").exists()
        assert not sig.exists()

    def test_appimage_signature_is_renamed_in_sync(self, dist_dir):
        src = dist_dir / "eCan-1.0.0-x86_64.AppImage"
        sig = dist_dir / "eCan-1.0.0-x86_64.AppImage.sig"
        src.write_bytes(b"appimage")
        sig.write_bytes(b"signature")

        bu._standardize_linux_artifacts("1.0.0", "amd64", "eCan")

        assert (dist_dir / "eCan-1.0.0-linux-amd64.AppImage").exists()
        assert (dist_dir / "eCan-1.0.0-linux-amd64.AppImage.sig").exists()
        assert not sig.exists()

    def test_app_short_name_overrides_default(self, dist_dir):
        src = dist_dir / "eCan.cn_1.0.0_amd64.deb"
        src.write_bytes(b"cn deb")
        bu._standardize_linux_artifacts("1.0.0", "amd64", "eCan.cn")
        assert (dist_dir / "eCan.cn-1.0.0-linux-amd64.deb").exists()


# ============================================================================
# Top-level dispatcher
# ============================================================================


class TestDispatcher:
    def test_windows_dispatch(self, dist_dir, monkeypatch):
        # The dispatcher reads platform.system() once. Monkeypatch
        # platform.system at module level to return "Windows".
        import build_system.build_utils as mod

        monkeypatch.setattr(mod.platform, "system", lambda: "Windows")

        src = dist_dir / "eCan Setup 1.0.0.exe"
        src.write_bytes(b"installer")
        bu.standardize_artifact_names("1.0.0", "amd64", "eCan")
        assert (dist_dir / "eCan-1.0.0-windows-amd64-Setup.exe").exists()

    def test_macos_dispatch(self, dist_dir, monkeypatch):
        import build_system.build_utils as mod

        monkeypatch.setattr(mod.platform, "system", lambda: "Darwin")

        src = dist_dir / "eCan-1.0.0.pkg"
        src.write_bytes(b"pkg")
        bu.standardize_artifact_names("1.0.0", "amd64", "eCan")
        assert (dist_dir / "eCan-1.0.0-macos-amd64.pkg").exists()

    def test_linux_dispatch(self, dist_dir, monkeypatch):
        import build_system.build_utils as mod

        monkeypatch.setattr(mod.platform, "system", lambda: "Linux")

        src = dist_dir / "eCan_1.0.0_amd64.deb"
        src.write_bytes(b"deb")
        bu.standardize_artifact_names("1.0.0", "amd64", "eCan")
        assert (dist_dir / "eCan-1.0.0-linux-amd64.deb").exists()

    def test_unsupported_platform_is_noop(self, dist_dir, monkeypatch):
        import build_system.build_utils as mod

        monkeypatch.setattr(mod.platform, "system", lambda: "Plan9")
        # Must not crash.
        bu.standardize_artifact_names("1.0.0", "amd64", "eCan")
        # Nothing was created or moved.
        assert list(dist_dir.iterdir()) == []