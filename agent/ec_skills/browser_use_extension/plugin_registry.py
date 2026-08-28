"""
Plugin Registry — per-user state for installed plugin bundles.

The registry tracks plugins that the user has installed via the Plugins GUI
(or programmatically). It is the single source of truth for: install source,
enabled flag, install path, version, and the result of the last signature
check.

In-tree bundles under ``hooks/external/`` are *not* tracked here — they are
shipped with the app, always considered installed and always enabled.
``list_all()`` merges both views so callers see one unified plugin list.

Storage
-------
Registry lives at ``<appdata>/plugins/registry.json`` (platform-aware via
``config.envi.getECBotDataHome``). Writes are atomic via temp + rename.

Public API
----------
- ``plugins_dir()`` / ``registry_path()`` — resolved on-demand so tests can
  monkeypatch ``app_info.appdata_path``.
- ``PluginEntry`` — pydantic model; the unit of read/write.
- ``load_registry`` / ``save_registry``
- ``list_installed`` — only user-installed; ``list_all`` — installed + in-tree.
- ``get(name)``
- ``set_enabled(name, enabled)``
- ``record_install(...)`` / ``record_uninstall(name)``
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from .hook_loader import list_available_bundles

from utils.logger_helper import logger_helper as logger  # CN app logger is "eCan.cn"

InstallSource = Literal["builtin", "local", "catalog"]
SignatureStatus = Literal["trusted", "verified", "unsigned", "untrusted", "n/a"]


class PluginEntry(BaseModel):
    """One row in registry.json plus runtime-derived fields.

    Persisted fields: everything except ``manifest_summary`` which is
    re-derived from the on-disk bundle on each list call.
    """

    name: str
    version: str = "0.0.0"
    kind: str = "hook_bundle"
    install_source: InstallSource = "local"
    install_path: str = ""
    enabled: bool = True
    installed_at: float = 0.0
    signature_status: SignatureStatus = "unsigned"

    # Runtime-derived (not persisted in registry.json — recomputed each call).
    manifest_summary: dict[str, Any] = Field(default_factory=dict)


# Single in-process lock — registry writes happen from IPC handlers and
# possibly from autoload at boot. Cross-process safety is out of scope for
# Phase 1 (single eCan process per user).
_REGISTRY_LOCK = threading.Lock()


def plugins_dir() -> Path:
    """Resolve the per-user plugins directory.

    Resolved fresh each call so tests can monkeypatch
    ``app_info.appdata_path``.
    """
    from config.envi import getECBotDataHome
    return Path(getECBotDataHome()) / "plugins"


def registry_path() -> Path:
    return plugins_dir() / "registry.json"


def _ensure_plugins_dir() -> Path:
    p = plugins_dir()
    p.mkdir(parents=True, exist_ok=True)
    return p


def load_registry() -> dict[str, PluginEntry]:
    """Load registry.json. Returns empty dict if file missing or unreadable."""
    path = registry_path()
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"[PluginRegistry] registry.json unreadable ({e}); starting empty")
        return {}
    if not isinstance(raw, dict):
        logger.warning(f"[PluginRegistry] registry.json root must be object, got {type(raw).__name__}")
        return {}
    out: dict[str, PluginEntry] = {}
    for name, entry_data in raw.items():
        if not isinstance(entry_data, dict):
            continue
        try:
            entry = PluginEntry.model_validate({**entry_data, "name": name})
            out[name] = entry
        except Exception as e:
            logger.warning(f"[PluginRegistry] dropping malformed entry {name!r}: {e}")
    return out


def save_registry(registry: dict[str, PluginEntry]) -> None:
    """Atomic write: serialize to temp file in the same dir, then rename."""
    _ensure_plugins_dir()
    target = registry_path()
    # Exclude runtime-derived fields from persistence.
    payload = {
        name: entry.model_dump(exclude={"name", "manifest_summary"})
        for name, entry in registry.items()
    }
    data = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)

    # Use NamedTemporaryFile in the same directory so the rename is atomic
    # on the same filesystem.
    fd, tmp_path = tempfile.mkstemp(prefix=".registry.", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(data)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        os.replace(tmp_path, target)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def list_installed() -> list[PluginEntry]:
    """Return user-installed plugins (registry rows only, no in-tree)."""
    with _REGISTRY_LOCK:
        reg = load_registry()
    out: list[PluginEntry] = []
    for entry in reg.values():
        _attach_manifest_summary(entry)
        out.append(entry)
    out.sort(key=lambda e: e.name)
    return out


def list_all() -> list[PluginEntry]:
    """Return installed + in-tree (builtin) plugins as a unified list.

    In-tree bundles always show ``install_source="builtin"`` and
    ``enabled=True``; users can't disable shipped bundles via the registry.
    """
    out: dict[str, PluginEntry] = {}

    # In-tree (builtin) bundles first.
    try:
        for raw in list_available_bundles():
            kind = _kind_from_manifest_summary(raw)
            entry = PluginEntry(
                name=str(raw.get("name") or raw.get("path") or ""),
                version=str(raw.get("version") or "0.0.0"),
                kind=kind,
                install_source="builtin",
                install_path=str(raw.get("abs_path") or ""),
                enabled=True,
                installed_at=0.0,
                signature_status=("verified" if raw.get("signed") else "n/a"),
                manifest_summary=_summary_from_raw(raw),
            )
            if entry.name:
                out[entry.name] = entry
    except Exception as e:
        logger.warning(f"[PluginRegistry] scan of in-tree bundles failed: {e}")

    # User-installed bundles override or add on top.
    with _REGISTRY_LOCK:
        reg = load_registry()
    for entry in reg.values():
        _attach_manifest_summary(entry)
        out[entry.name] = entry

    items = list(out.values())
    items.sort(key=lambda e: e.name)
    return items


def get(name: str) -> Optional[PluginEntry]:
    """Lookup a single plugin by name (installed OR builtin)."""
    for e in list_all():
        if e.name == name:
            return e
    return None


def set_enabled(name: str, enabled: bool) -> bool:
    """Toggle enabled flag for a user-installed plugin.

    In-tree bundles can't be disabled here (the user must opt out per-node
    via the skill editor's hookBundles entry). Returns True on success.
    """
    with _REGISTRY_LOCK:
        reg = load_registry()
        entry = reg.get(name)
        if entry is None:
            return False
        if entry.enabled == enabled:
            return True
        entry.enabled = enabled
        reg[name] = entry
        save_registry(reg)
    logger.info(f"[PluginRegistry] {name!r} enabled={enabled}")
    return True


def record_install(
    name: str,
    *,
    version: str,
    install_source: InstallSource,
    install_path: str,
    kind: str = "hook_bundle",
    signature_status: SignatureStatus = "unsigned",
    enabled: bool = True,
) -> PluginEntry:
    """Insert or overwrite a registry row after an install/update."""
    entry = PluginEntry(
        name=name,
        version=version,
        kind=kind,
        install_source=install_source,
        install_path=install_path,
        enabled=enabled,
        installed_at=time.time(),
        signature_status=signature_status,
    )
    with _REGISTRY_LOCK:
        reg = load_registry()
        reg[name] = entry
        save_registry(reg)
    logger.info(
        f"[PluginRegistry] recorded install: {name} v{version} "
        f"({install_source}) at {install_path}"
    )
    return entry


def record_uninstall(name: str) -> bool:
    """Remove a row from the registry. Returns True if removed."""
    with _REGISTRY_LOCK:
        reg = load_registry()
        if name not in reg:
            return False
        del reg[name]
        save_registry(reg)
    logger.info(f"[PluginRegistry] recorded uninstall: {name}")
    return True


# ---------------------------------------------------------------------------
# Manifest summary helpers — read live from disk so the GUI always sees
# current values without us having to migrate the registry on every change.
# ---------------------------------------------------------------------------
def _attach_manifest_summary(entry: PluginEntry) -> None:
    """Populate ``manifest_summary`` on a registry-loaded entry by reading
    the bundle's hook.yaml from ``install_path``. Silently no-ops on error.
    """
    if not entry.install_path:
        return
    bundle_dir = Path(entry.install_path)
    if not bundle_dir.is_dir():
        return
    try:
        # Reuse hook_loader's parser via list_available_bundles on the
        # parent dir — cheap, since the parent contains only one bundle
        # we care about. For one-off lookups we just inline the read.
        from .hook_loader import _read_manifest_file  # type: ignore[attr-defined]
        data = _read_manifest_file(bundle_dir)
    except Exception:
        return
    entry.manifest_summary = _summary_from_raw({
        "name": data.get("bundle") or bundle_dir.name,
        "version": data.get("version") or "0.0.0",
        "author": data.get("author") or "",
        "description": (data.get("description") or "").strip(),
        "hooks": data.get("hooks") or [],
        "config_defaults": data.get("config") or {},
        "config_schema": data.get("config_schema") or None,
        "kind": data.get("kind") or "hook_bundle",
        "gui": data.get("gui"),
    })
    # Backfill kind from manifest if registry row was written before kind
    # was a tracked field.
    if entry.kind == "hook_bundle" and entry.manifest_summary.get("kind"):
        entry.kind = entry.manifest_summary["kind"]


def _kind_from_manifest_summary(raw: dict) -> str:
    """Derive ``kind`` for an in-tree bundle row (list_available_bundles
    doesn't currently emit `kind`; we read it from the manifest path).
    """
    abs_path = raw.get("abs_path")
    if not abs_path:
        return "hook_bundle"
    try:
        from .hook_loader import _read_manifest_file  # type: ignore[attr-defined]
        data = _read_manifest_file(Path(abs_path))
        return str(data.get("kind") or "hook_bundle")
    except Exception:
        return "hook_bundle"


def _summary_from_raw(raw: dict) -> dict[str, Any]:
    """Flatten the fields the GUI cares about into a stable shape."""
    return {
        "author": raw.get("author") or "",
        "description": (raw.get("description") or "").strip(),
        "hooks": [
            {
                "name": h.get("name"),
                "stage": h.get("stage"),
                "runtime": h.get("runtime") or "python",
                "tier": h.get("tier"),
                "priority": h.get("priority"),
            }
            for h in (raw.get("hooks") or [])
            if isinstance(h, dict)
        ],
        "config_defaults": dict(raw.get("config_defaults") or {}),
        "config_schema": raw.get("config_schema") or None,
        "kind": raw.get("kind") or "hook_bundle",
        # Phase 3: surface the gui block so the GUI knows which slots are
        # declared without a second IPC roundtrip. Keep just the slot
        # entrypoints + heights + permissions — the actual files are
        # served via plugin_gui_server.
        "gui": (raw.get("gui") if isinstance(raw.get("gui"), dict) else None),
    }


__all__ = [
    "InstallSource",
    "SignatureStatus",
    "PluginEntry",
    "plugins_dir",
    "registry_path",
    "load_registry",
    "save_registry",
    "list_installed",
    "list_all",
    "get",
    "set_enabled",
    "record_install",
    "record_uninstall",
]
