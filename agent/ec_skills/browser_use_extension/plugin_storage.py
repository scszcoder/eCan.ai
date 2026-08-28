"""
Plugin Storage — per-bundle KV store accessed via the GUI bridge.

Each bundle gets a single JSON file under
``<plugins_dir>/<bundle>/storage.json``.  Reads/writes are gated by the
bridge so a plugin can only access its own namespace.

This is for plugin-GUI persistence (e.g. UI tab state, recent items,
cached form values) — NOT for plugin runtime state, which lives in the
hook's ``StateStore`` (memory/disk).  Keeping the two separated lets the
hook author iterate on the GUI without touching runtime persistence.

Limits
------
- Total file size capped at ``MAX_STORAGE_BYTES`` (1 MB).  A set() that
  would push the file past the cap raises ``StorageLimitError``.
- Top-level keys are strings; values are JSON-serializable.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from pathlib import Path
from typing import Any, Optional

from . import plugin_registry

from utils.logger_helper import logger_helper as logger  # CN app logger is "eCan.cn"

MAX_STORAGE_BYTES = 1_000_000  # 1 MB per bundle


class StorageError(Exception):
    """Base class for storage failures."""


class StorageLimitError(StorageError):
    """Raised when a set would push storage past the per-bundle cap."""


_LOCK = threading.Lock()


def _bundle_install_path(bundle: str) -> Path:
    """Return the install dir for a bundle (works for builtin AND user-installed)."""
    entry = plugin_registry.get(bundle)
    if entry is None or not entry.install_path:
        raise StorageError(f"unknown plugin: {bundle!r}")
    p = Path(entry.install_path)
    if not p.is_dir():
        raise StorageError(f"plugin install path missing: {p}")
    return p


def _storage_path(bundle: str) -> Path:
    """Return ``<install_path>/storage.json`` (file may not exist yet).

    Builtin bundles live in the source tree; for those we instead place
    storage under ``<plugins_dir>/_storage/<bundle>.json`` so we don't
    write into the source tree.
    """
    entry = plugin_registry.get(bundle)
    if entry is None:
        raise StorageError(f"unknown plugin: {bundle!r}")
    if entry.install_source == "builtin":
        root = plugin_registry.plugins_dir() / "_storage"
        root.mkdir(parents=True, exist_ok=True)
        return root / f"{bundle}.json"
    return _bundle_install_path(bundle) / "storage.json"


def _load(bundle: str) -> dict[str, Any]:
    path = _storage_path(bundle)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"[PluginStorage] {bundle!r} storage.json unreadable ({e}); starting empty")
        return {}
    return data if isinstance(data, dict) else {}


def _save(bundle: str, data: dict[str, Any]) -> None:
    encoded = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)
    if len(encoded.encode("utf-8")) > MAX_STORAGE_BYTES:
        raise StorageLimitError(
            f"plugin {bundle!r} storage exceeds {MAX_STORAGE_BYTES} bytes; "
            f"trim or split your KV before writing"
        )
    path = _storage_path(bundle)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".storage.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(encoded)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def get(bundle: str, key: str, default: Any = None) -> Any:
    """Return ``storage[key]`` or ``default`` when missing."""
    with _LOCK:
        return _load(bundle).get(key, default)


def set(bundle: str, key: str, value: Any) -> None:  # noqa: A001 (shadows builtin on purpose for parity)
    """Set a single key. Raises StorageLimitError if the file would exceed cap."""
    if not isinstance(key, str) or not key:
        raise StorageError("storage key must be a non-empty string")
    # Sanity check: value must be JSON-serializable.
    try:
        json.dumps(value)
    except Exception as e:
        raise StorageError(f"value for {key!r} is not JSON-serializable: {e}") from e
    with _LOCK:
        data = _load(bundle)
        data[key] = value
        _save(bundle, data)


def delete(bundle: str, key: str) -> bool:
    """Remove a key. Returns True if it existed."""
    with _LOCK:
        data = _load(bundle)
        if key not in data:
            return False
        del data[key]
        _save(bundle, data)
        return True


def keys(bundle: str) -> list[str]:
    """Return sorted list of keys currently set."""
    with _LOCK:
        return sorted(_load(bundle).keys())


def snapshot(bundle: str) -> dict[str, Any]:
    """Return a copy of the full storage dict (for diagnostics)."""
    with _LOCK:
        return dict(_load(bundle))


__all__ = [
    "MAX_STORAGE_BYTES",
    "StorageError",
    "StorageLimitError",
    "get",
    "set",
    "delete",
    "keys",
    "snapshot",
]
