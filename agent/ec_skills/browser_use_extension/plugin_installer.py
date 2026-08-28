"""
Plugin Installer — local install / uninstall flows.

Phase 1 scope: install from a zip file or a directory on disk. Catalog
install (HTTPS download from the canonical catalog) lands in Phase 3 and
will reuse ``_finalize_install`` from this module.

Install pipeline
----------------
1. Locate source (zip file or directory).
2. Extract to a temp dir under ``<appdata>/plugins/_staging/`` so we never
   leave a half-written bundle in the live install dir.
3. Validate the manifest:
   - hook.yaml or hook.json must exist.
   - bundle field present and matches a directory-name-safe slug.
   - each hook entry parses via ``HookManifest`` (catches tier=0, bad
     entrypoint shape, unsupported api version).
4. Compute signature status (best-effort; we don't enforce signing in
   Phase 1 — that's a Phase 3 concern).
5. Atomically move staged dir → ``<plugins_dir>/<bundle_name>/`` (replacing
   any prior version of the same bundle).
6. Record in the registry.

Uninstall pipeline
------------------
1. Look up entry; refuse if not in registry (builtin bundles can't be
   uninstalled this way).
2. Refuse if ``find_dependents`` returns non-empty, unless ``force=True``.
3. ``shutil.rmtree`` the install dir.
4. Remove the registry row.
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from . import plugin_dependents, plugin_registry
from .hook_loader import (
    BundleManifestError,
    _build_hook_manifest,  # type: ignore[attr-defined]
    _read_manifest_file,  # type: ignore[attr-defined]
)
from .hook_api import HOOK_API_VERSION

from utils.logger_helper import logger_helper as logger  # CN app logger is "eCan.cn"


# Bundle names map to directory names; keep them strict.
_VALID_NAME_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-.")


class PluginInstallerError(Exception):
    """Base class for installer-side failures."""


class InvalidBundleError(PluginInstallerError):
    """Source is not a valid bundle (missing manifest, bad name, etc.)."""


class DependentsBlockedError(PluginInstallerError):
    """Uninstall refused because the bundle is still referenced."""

    def __init__(self, message: str, dependents: list[plugin_dependents.Dependent]):
        super().__init__(message)
        self.dependents = dependents


@dataclass(frozen=True)
class InstallResult:
    name: str
    version: str
    install_path: str
    install_source: plugin_registry.InstallSource
    signature_status: plugin_registry.SignatureStatus
    kind: str


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def install_from_zip(zip_path: Path | str) -> InstallResult:
    """Install a plugin from a zip archive.

    The zip is expected to contain either:
      (a) a single top-level directory that holds the bundle, or
      (b) the bundle files directly at the archive root.

    Returns an InstallResult; raises ``PluginInstallerError`` on failure.
    """
    zp = Path(zip_path).resolve()
    if not zp.is_file():
        raise PluginInstallerError(f"zip not found: {zp}")
    if not zipfile.is_zipfile(zp):
        raise PluginInstallerError(f"not a valid zip file: {zp}")

    staging_root = _staging_dir()
    staging_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="extract_", dir=str(staging_root)) as extract_tmp:
        extract_dir = Path(extract_tmp)
        try:
            with zipfile.ZipFile(zp, "r") as zf:
                _safe_extract_zip(zf, extract_dir)
        except PluginInstallerError:
            raise
        except Exception as e:
            raise PluginInstallerError(f"failed to extract {zp}: {e}") from e

        bundle_src = _find_bundle_root(extract_dir)
        return _finalize_install(bundle_src, install_source="local")


def install_from_dir(src_dir: Path | str, *, copy: bool = True) -> InstallResult:
    """Install a plugin from a directory on disk.

    ``copy=True`` (default) copies the directory into ``<plugins_dir>/<name>``.
    ``copy=False`` is reserved for a future dev-mode that symlinks; not
    implemented in Phase 1 and currently raises.
    """
    sp = Path(src_dir).resolve()
    if not sp.is_dir():
        raise PluginInstallerError(f"source dir not found: {sp}")
    if not copy:
        raise PluginInstallerError("copy=False (symlink/dev mode) not implemented in Phase 1")
    return _finalize_install(sp, install_source="local")


def uninstall(bundle: str, *, force: bool = False) -> None:
    """Remove an installed plugin. Raises if the bundle is unknown,
    is a builtin (can't be uninstalled here), or has dependents and
    ``force=False``.
    """
    entry = plugin_registry.get(bundle)
    if entry is None:
        raise PluginInstallerError(f"plugin not installed: {bundle!r}")
    if entry.install_source == "builtin":
        raise PluginInstallerError(
            f"plugin {bundle!r} is a builtin bundle and cannot be uninstalled "
            f"via the registry; remove it from the source tree instead"
        )

    deps = plugin_dependents.find_dependents(bundle)
    if deps and not force:
        raise DependentsBlockedError(
            f"plugin {bundle!r} is referenced by {len(deps)} skill node(s); "
            f"pass force=True to remove anyway",
            deps,
        )

    install_path = Path(entry.install_path)
    if install_path.is_dir():
        try:
            shutil.rmtree(install_path)
        except Exception as e:
            raise PluginInstallerError(
                f"failed to remove {install_path}: {e}"
            ) from e
    else:
        logger.warning(
            f"[PluginInstaller] uninstall: install path missing on disk: "
            f"{install_path} (cleaning registry anyway)"
        )

    plugin_registry.record_uninstall(bundle)


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------
def _staging_dir() -> Path:
    return plugin_registry.plugins_dir() / "_staging"


def _safe_extract_zip(zf: zipfile.ZipFile, dest: Path) -> None:
    """Extract a zip into ``dest`` with path-traversal protection.

    Rejects entries whose resolved path escapes ``dest``. Skips symlink
    entries entirely.
    """
    dest_abs = dest.resolve()
    for member in zf.infolist():
        name = member.filename
        # Normalize path separators and reject absolute paths.
        if name.startswith("/") or (len(name) >= 2 and name[1] == ":"):
            raise PluginInstallerError(f"zip contains absolute path: {name!r}")
        # Reject symlinks; we want a self-contained tree only.
        # External attr layout: high 16 bits hold the unix mode.
        mode = member.external_attr >> 16
        if mode and (mode & 0o170000) == 0o120000:  # S_IFLNK
            raise PluginInstallerError(f"zip contains symlink: {name!r}")
        target = (dest_abs / name).resolve()
        try:
            target.relative_to(dest_abs)
        except ValueError:
            raise PluginInstallerError(f"zip entry escapes dest: {name!r}")
    zf.extractall(dest_abs)


def _find_bundle_root(extract_dir: Path) -> Path:
    """Locate the bundle's hook.yaml/hook.json within the extracted tree.

    Accepts either of these layouts:
      extract_dir/hook.yaml                  → return extract_dir
      extract_dir/<single_subdir>/hook.yaml  → return extract_dir/<single_subdir>
    """
    for fname in ("hook.yaml", "hook.json"):
        if (extract_dir / fname).is_file():
            return extract_dir
    subdirs = [p for p in extract_dir.iterdir() if p.is_dir() and not p.name.startswith(".")]
    if len(subdirs) == 1:
        only = subdirs[0]
        if (only / "hook.yaml").is_file() or (only / "hook.json").is_file():
            return only
    raise InvalidBundleError(
        f"could not locate hook.yaml or hook.json inside the archive "
        f"(found: {[p.name for p in extract_dir.iterdir()]})"
    )


def _validate_manifest(bundle_dir: Path) -> tuple[str, str, str, dict]:
    """Parse and validate the manifest. Returns (name, version, kind, raw_dict).

    Raises InvalidBundleError on any validation failure.
    """
    try:
        data = _read_manifest_file(bundle_dir)
    except Exception as e:
        raise InvalidBundleError(f"manifest unreadable: {e}") from e

    bundle_name = str(data.get("bundle") or "").strip()
    if not bundle_name:
        raise InvalidBundleError("manifest missing required 'bundle' field")
    if any(ch not in _VALID_NAME_CHARS for ch in bundle_name):
        raise InvalidBundleError(
            f"bundle name {bundle_name!r} contains invalid characters; "
            f"allowed: a-z A-Z 0-9 _ - ."
        )

    raw_hooks = data.get("hooks")
    if not isinstance(raw_hooks, list) or not raw_hooks:
        raise InvalidBundleError(f"bundle {bundle_name!r} must declare a non-empty 'hooks' list")

    api_version = int(data.get("api_version") or HOOK_API_VERSION)
    for entry in raw_hooks:
        if not isinstance(entry, dict):
            raise InvalidBundleError(
                f"bundle {bundle_name!r} has a non-dict hook entry: {entry!r}"
            )
        try:
            _build_hook_manifest(bundle_name, entry, api_version)
        except BundleManifestError as e:
            raise InvalidBundleError(str(e)) from e
        except Exception as e:  # IncompatibleHookApiVersion, TierViolation, etc.
            raise InvalidBundleError(
                f"bundle {bundle_name!r} hook {entry.get('name')!r}: {e}"
            ) from e

    version = str(data.get("version") or "0.0.0")
    kind = str(data.get("kind") or "hook_bundle")
    return bundle_name, version, kind, data


def _detect_signature_status(bundle_dir: Path) -> plugin_registry.SignatureStatus:
    """Best-effort signature classification for Phase 1.

    We don't actually verify HMAC keys here (that's gated by EC_HOOK_TRUST_MODE
    inside hook_loader.enforce_trust during load_bundle). We just note whether
    a hook.sig is present so the GUI can show a status badge.
    """
    if (bundle_dir / "hook.sig").is_file():
        return "verified"
    return "unsigned"


def _finalize_install(
    src_bundle_dir: Path,
    *,
    install_source: plugin_registry.InstallSource,
) -> InstallResult:
    """Validate, atomically move into place, and record the registry row."""
    bundle_name, version, kind, _raw = _validate_manifest(src_bundle_dir)

    plugins_root = plugin_registry.plugins_dir()
    plugins_root.mkdir(parents=True, exist_ok=True)

    target = plugins_root / bundle_name

    # If the source IS already the target (re-install from same dir), nothing to move.
    if src_bundle_dir.resolve() == target.resolve():
        sig_status = _detect_signature_status(target)
        plugin_registry.record_install(
            bundle_name,
            version=version,
            install_source=install_source,
            install_path=str(target),
            kind=kind,
            signature_status=sig_status,
        )
        return InstallResult(
            name=bundle_name, version=version, install_path=str(target),
            install_source=install_source, signature_status=sig_status, kind=kind,
        )

    # Two-step atomic install:
    #   1. Copy source to a staging directory under plugins_root (same FS so
    #      the final rename is atomic).
    #   2. If target exists, rename it to a backup name, then rename staging
    #      → target. On success delete backup; on failure roll back.
    staging_root = _staging_dir()
    staging_root.mkdir(parents=True, exist_ok=True)
    staged = staging_root / f"{bundle_name}.{int(time.time() * 1000)}.staged"
    if staged.exists():
        shutil.rmtree(staged)
    shutil.copytree(src_bundle_dir, staged)

    backup: Optional[Path] = None
    try:
        if target.exists():
            backup = target.with_name(target.name + f".bak.{int(time.time() * 1000)}")
            os.replace(target, backup)
        os.replace(staged, target)
    except Exception:
        # Roll back on failure.
        if backup is not None and backup.exists() and not target.exists():
            try:
                os.replace(backup, target)
            except Exception:
                pass
        if staged.exists():
            try:
                shutil.rmtree(staged)
            except Exception:
                pass
        raise
    else:
        if backup is not None and backup.exists():
            try:
                shutil.rmtree(backup)
            except Exception:
                logger.warning(f"[PluginInstaller] failed to clean backup at {backup}")

    sig_status = _detect_signature_status(target)
    plugin_registry.record_install(
        bundle_name,
        version=version,
        install_source=install_source,
        install_path=str(target),
        kind=kind,
        signature_status=sig_status,
    )
    return InstallResult(
        name=bundle_name, version=version, install_path=str(target),
        install_source=install_source, signature_status=sig_status, kind=kind,
    )


__all__ = [
    "PluginInstallerError",
    "InvalidBundleError",
    "DependentsBlockedError",
    "InstallResult",
    "install_from_zip",
    "install_from_dir",
    "uninstall",
]
