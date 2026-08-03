"""
Plugin Config — per-bundle global configuration (vs per-node config which
lives inside skill JSON's hookBundles entries).

Persisted at ``<plugins_dir>/<bundle>/config.json`` for user-installed
bundles, or ``<plugins_dir>/_config/<bundle>.json`` for builtins (so we
don't write into the source tree).

The shape stored on disk is the merged user-visible config — exactly what
gets passed to the dispatcher as ``HookBundleSpec.config`` when the
bundle is loaded.  Manifest defaults (``hook.yaml`` ``config:`` block)
are baked in by the consumer; the file only holds user overrides.

Validation
----------
When the bundle's manifest declares a ``config_schema``, set() does a
minimal type check against the schema.  We don't do full JSON-Schema
draft-7 validation (the frontend renders typed widgets which already
enforce types); the check here is a guard against IPC-level abuse.
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

logger = logging.getLogger("eCan")


class ConfigError(Exception):
    """Base class for config failures."""


class ConfigValidationError(ConfigError):
    """Raised when a value doesn't match the bundle's config_schema."""


_LOCK = threading.Lock()


def _config_path(bundle: str) -> Path:
    entry = plugin_registry.get(bundle)
    if entry is None:
        raise ConfigError(f"unknown plugin: {bundle!r}")
    if entry.install_source == "builtin":
        root = plugin_registry.plugins_dir() / "_config"
        root.mkdir(parents=True, exist_ok=True)
        return root / f"{bundle}.json"
    p = Path(entry.install_path)
    p.mkdir(parents=True, exist_ok=True)
    return p / "config.json"


def _manifest_schema(bundle: str) -> Optional[dict]:
    entry = plugin_registry.get(bundle)
    if entry is None:
        return None
    schema = entry.manifest_summary.get("config_schema")
    return schema if isinstance(schema, dict) else None


def _load(bundle: str) -> dict[str, Any]:
    path = _config_path(bundle)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"[PluginConfig] {bundle!r} config.json unreadable ({e}); starting empty")
        return {}
    return data if isinstance(data, dict) else {}


def _save(bundle: str, data: dict[str, Any]) -> None:
    path = _config_path(bundle)
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)
    fd, tmp = tempfile.mkstemp(prefix=".config.", suffix=".tmp", dir=str(path.parent))
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


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def get(bundle: str) -> dict[str, Any]:
    """Return the persisted user-overridden config (empty dict when unset)."""
    with _LOCK:
        return _load(bundle)


def merged(bundle: str) -> dict[str, Any]:
    """Return manifest_defaults ∪ user_overrides (overrides win).

    This is what the dispatcher will see at runtime once we wire global
    config into autoload (future task — Phase 1 autoload uses defaults only).
    """
    entry = plugin_registry.get(bundle)
    if entry is None:
        return {}
    defaults = dict(entry.manifest_summary.get("config_defaults") or {})
    with _LOCK:
        overrides = _load(bundle)
    return {**defaults, **overrides}


def set(bundle: str, patch: dict[str, Any]) -> dict[str, Any]:  # noqa: A001
    """Merge ``patch`` into the persisted config and return the new full config.

    Pass an empty dict to clear (the entire override file is rewritten;
    keys not in patch but present before are preserved).
    """
    if not isinstance(patch, dict):
        raise ConfigError("patch must be an object")

    schema = _manifest_schema(bundle)
    if schema:
        _shallow_validate(patch, schema)

    with _LOCK:
        data = _load(bundle)
        data.update(patch)
        _save(bundle, data)
        return dict(data)


def replace(bundle: str, full: dict[str, Any]) -> dict[str, Any]:
    """Replace the full stored config (no merge). Schema-checked."""
    if not isinstance(full, dict):
        raise ConfigError("config must be an object")
    schema = _manifest_schema(bundle)
    if schema:
        _shallow_validate(full, schema)
    with _LOCK:
        _save(bundle, full)
        return dict(full)


def clear(bundle: str) -> None:
    """Remove the persisted override file entirely."""
    path = _config_path(bundle)
    with _LOCK:
        try:
            if path.is_file():
                os.unlink(path)
        except OSError as e:
            raise ConfigError(f"could not remove config file: {e}") from e


# ---------------------------------------------------------------------------
# Minimal shallow validation against config_schema.
# ---------------------------------------------------------------------------
def _shallow_validate(patch: dict[str, Any], schema: dict) -> None:
    """Best-effort type check.

    Covers: type=string/integer/number/boolean, enum, and the
    object-of-strings shape used by the reference bundle.  Doesn't enforce required
    or recurse into nested objects beyond one level (good enough for the
    schemas the frontend renders).
    """
    if schema.get("type") != "object":
        return
    properties = schema.get("properties") or {}
    if not isinstance(properties, dict):
        return
    for key, value in patch.items():
        prop = properties.get(key)
        if not isinstance(prop, dict):
            continue  # additionalProperties → no type to enforce
        _check_value(key, value, prop)


def _check_value(key: str, value: Any, prop: dict) -> None:
    t = prop.get("type")
    if t == "string":
        if not isinstance(value, str):
            raise ConfigValidationError(f"{key!r} must be a string, got {type(value).__name__}")
        if "enum" in prop and isinstance(prop["enum"], list) and value not in prop["enum"]:
            raise ConfigValidationError(f"{key!r} must be one of {prop['enum']!r}")
    elif t == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            raise ConfigValidationError(f"{key!r} must be an integer, got {type(value).__name__}")
        if "minimum" in prop and value < prop["minimum"]:
            raise ConfigValidationError(f"{key!r} must be >= {prop['minimum']}")
        if "maximum" in prop and value > prop["maximum"]:
            raise ConfigValidationError(f"{key!r} must be <= {prop['maximum']}")
    elif t == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ConfigValidationError(f"{key!r} must be a number, got {type(value).__name__}")
    elif t == "boolean":
        if not isinstance(value, bool):
            raise ConfigValidationError(f"{key!r} must be a boolean, got {type(value).__name__}")
    elif t == "object":
        if not isinstance(value, dict):
            raise ConfigValidationError(f"{key!r} must be an object, got {type(value).__name__}")
        ap = prop.get("additionalProperties")
        if isinstance(ap, dict) and ap.get("type") == "string":
            for k, v in value.items():
                if not isinstance(v, str):
                    raise ConfigValidationError(
                        f"{key!r}.{k!r} must be a string (object-of-strings), got {type(v).__name__}"
                    )


__all__ = [
    "ConfigError",
    "ConfigValidationError",
    "get",
    "merged",
    "set",
    "replace",
    "clear",
]
