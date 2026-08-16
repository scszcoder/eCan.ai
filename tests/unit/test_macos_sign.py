"""
Unit tests for build_system/build_utils.sign_macos_prod.

The actual `codesign` / `notarytool` / `stapler` subprocess pipeline is
NOT covered here — it requires a real macOS runner with a real
Developer ID. These tests pin the gate behaviour:

  1. On non-Darwin platforms: no-op (returns True, logs "Skipped").
  2. On Darwin with one or more required env vars missing: no-op.
  3. The list of required env vars is stable (regression guard).

The intent is that the existing un-signed-and-un-notarized behaviour
is preserved exactly when secrets are NOT configured, and that a
future refactor cannot silently re-enable signing without explicit
configuration. The UNVERIFIED flag in the function's docstring is
the live tracker for the end-to-end smoke.

Tests below use `_mac_sign_is_configured()` directly because it is
the single source of truth for the gate decision. `sign_macos_prod()`
is also exercised indirectly via the platform + env mocks.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest import mock

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from build_system import build_utils as bu  # noqa: E402


# All six env vars the workflow injects. Any one missing → no-op.
_REQUIRED_VARS = (
    "MAC_CODESIGN_IDENTITY",
    "MAC_CERT_P12",
    "MAC_CERT_PASSWORD",
    "APPLE_ID",
    "APPLE_APP_SPECIFIC_PASSWORD",
    "TEAM_ID",
)


def _set_all_required(monkeypatch, **overrides):
    """Set every required env var to a sentinel non-NOT_SET value.
    Pass overrides to change one or more values."""
    for name in _REQUIRED_VARS:
        monkeypatch.setenv(name, overrides.get(name, "test-value"))
    # Clear NOT_SET explicitly so a stale value doesn't linger
    # from a previous test in the same process.
    for name in _REQUIRED_VARS:
        monkeypatch.delenv(name, raising=False)
    for name in _REQUIRED_VARS:
        monkeypatch.setenv(name, overrides.get(name, "test-value"))


# ---------------------------------------------------------------------------
# _mac_sign_is_configured
# ---------------------------------------------------------------------------


def test_is_configured_true_when_all_vars_set(monkeypatch):
    """Happy path: all six env vars present and non-empty → ready to sign."""
    _set_all_required(monkeypatch)
    assert bu._mac_sign_is_configured() is True


def test_is_configured_false_when_one_var_missing(monkeypatch):
    """Any single missing var → not configured. The six vars are AND-ed."""
    _set_all_required(monkeypatch)
    monkeypatch.delenv("MAC_CERT_P12")
    assert bu._mac_sign_is_configured() is False


@pytest.mark.parametrize("missing", _REQUIRED_VARS)
def test_is_configured_false_for_each_missing_var(monkeypatch, missing):
    """Regression guard: if a future refactor adds a 7th required var,
    this parametrize list should be updated to match. The point is
    that no single var is "obviously optional" — every one gates."""
    _set_all_required(monkeypatch)
    monkeypatch.delenv(missing)
    assert bu._mac_sign_is_configured() is False, (
        f"removing {missing} should disable signing; if this assertion "
        f"fails, _mac_sign_is_configured has been relaxed"
    )


def test_is_configured_false_when_var_set_to_not_set(monkeypatch):
    """The workflow injects `|| 'NOT_SET'` as a sentinel for missing
    secrets (see release-{intl,cn}.yml). `_mac_sign_is_configured`
    must treat that as missing, otherwise an UNCONFIGURED runner
    would attempt to sign with the literal string 'NOT_SET'."""
    _set_all_required(monkeypatch, MAC_CERT_PASSWORD="NOT_SET")
    assert bu._mac_sign_is_configured() is False


def test_is_configured_false_when_var_empty_string(monkeypatch):
    """Empty string is also a valid "secret not injected" signal."""
    _set_all_required(monkeypatch, APPLE_ID="")
    assert bu._mac_sign_is_configured() is False


def test_is_configured_false_when_no_vars_at_all(monkeypatch):
    """Baseline: with nothing set, no signing happens."""
    for name in _REQUIRED_VARS:
        monkeypatch.delenv(name, raising=False)
    assert bu._mac_sign_is_configured() is False


# ---------------------------------------------------------------------------
# sign_macos_prod — gate behaviour
# ---------------------------------------------------------------------------


def test_sign_macos_prod_no_op_on_linux(monkeypatch):
    """On non-Darwin, even with all secrets set, the function must
    be a no-op. Otherwise a CI runner that's already produced an
    .app on macOS could attempt to sign it on a Linux runner that
    happens to have MAC_* env vars set."""
    _set_all_required(monkeypatch)
    with mock.patch("platform.system", return_value="Linux"):
        # The function must NOT touch dist/ at all on Linux — it
        # should return True (no-op) before any subprocess call.
        assert bu.sign_macos_prod() is True


def test_sign_macos_prod_no_op_on_windows(monkeypatch):
    """Symmetric to Linux."""
    _set_all_required(monkeypatch)
    with mock.patch("platform.system", return_value="Windows"):
        assert bu.sign_macos_prod() is True


def test_sign_macos_prod_no_op_on_darwin_without_secrets(monkeypatch):
    """On macOS without secrets: no-op (returns True). This is the
    current behaviour and we must preserve it until secrets are
    configured — otherwise the un-signed-and-un-notarized default
    silently becomes a sign-with-empty-identity failure."""
    for name in _REQUIRED_VARS:
        monkeypatch.delenv(name, raising=False)
    with mock.patch("platform.system", return_value="Darwin"):
        assert bu.sign_macos_prod() is True


def test_sign_macos_prod_no_op_on_darwin_with_partial_secrets(monkeypatch):
    """On macOS with SOME but not ALL secrets: no-op (returns True).
    Prevents the failure mode where 3 of 6 vars are set and the
    function attempts `codesign --sign NOT_SET`, which would
    fail with a confusing error."""
    _set_all_required(monkeypatch)
    monkeypatch.delenv("TEAM_ID")
    with mock.patch("platform.system", return_value="Darwin"):
        assert bu.sign_macos_prod() is True


def test_sign_macos_prod_full_config_returns_false_when_no_app_bundle(monkeypatch, tmp_path):
    """On macOS with all secrets AND no .app bundle in dist/: fail
    (returns False) — there is genuinely nothing to sign. This
    distinguishes the no-op gates (return True) from a real failure
    (return False), so the workflow can decide whether to fail the
    build or just log a warning."""
    _set_all_required(monkeypatch)
    with mock.patch("platform.system", return_value="Darwin"), \
         mock.patch.object(bu, "_mac_sign_resolve_app_bundle", return_value=None):
        assert bu.sign_macos_prod() is False


def test_mac_sign_resolve_app_bundle_returns_none_when_dist_missing(tmp_path):
    """`_mac_sign_resolve_app_bundle` accepts an explicit `dist_dir`
    so tests (and a future refactor that wants to sign a non-default
    bundle) can override the default project_root lookup. Pass a
    path that doesn't exist → returns None without raising."""
    assert bu._mac_sign_resolve_app_bundle(dist_dir=tmp_path / "no-such-dist") is None


def test_mac_sign_resolve_app_bundle_returns_none_on_non_darwin(monkeypatch):
    """Non-Darwin runner: skip the lookup entirely. The function
    short-circuits BEFORE touching the filesystem so the
    `dist_dir` argument is irrelevant on Linux/Windows."""
    with mock.patch("platform.system", return_value="Linux"):
        # Pass None explicitly to make sure we don't accidentally
        # exercise the default-arg branch on non-Darwin.
        assert bu._mac_sign_resolve_app_bundle(dist_dir=None) is None


def test_mac_sign_resolve_app_bundle_finds_app(tmp_path):
    """Happy path: dist/eCan.app exists, return its path."""
    (tmp_path / "dist").mkdir()
    app = tmp_path / "dist" / "eCan.app"
    app.mkdir()
    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setattr(bu.Path, "resolve",
                            lambda self: tmp_path / self if isinstance(self, str) else self)
        # The function builds a project_root from `__file__`. To
        # avoid touching the real repo, we directly exercise
        # `_mac_sign_resolve_app_bundle(dist_dir=...)`.
        assert bu._mac_sign_resolve_app_bundle(dist_dir=tmp_path / "dist") == app
    finally:
        monkeypatch.undo()


def test_mac_sign_resolve_app_bundle_prefers_alphabetical_first(tmp_path):
    """Multiple .app bundles: pick the alphabetically first. The
    function logs a WARNING so the build is auditable, but it
    doesn't fail — the build pipeline produces exactly one bundle
    per channel so this is purely a safety net."""
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "z-late.app").mkdir()
    (tmp_path / "dist" / "a-early.app").mkdir()
    resolved = bu._mac_sign_resolve_app_bundle(dist_dir=tmp_path / "dist")
    assert resolved is not None
    assert resolved.name == "a-early.app"