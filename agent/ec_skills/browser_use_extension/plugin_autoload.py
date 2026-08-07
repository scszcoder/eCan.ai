"""
Plugin Autoload — warm-load enabled user-installed bundles on app boot.

Phase 1 semantics:
  - "warm-load" = call ``hook_loader.load_bundle`` so the manifest is parsed,
    the Python entrypoint is imported, and the Hook instance is constructed
    and cached. First node-attach later in the run pays no import cost.
  - "no auto-attach" = we do NOT register these hooks against every
    PrivacyAgent instance. Per-node ``hookBundles`` JSON is still the
    attach surface. The skill editor (Phase 2) shows the warmed bundles in
    a multi-select dropdown.

Concurrency: ``initialize()`` is idempotent. Calling it twice does nothing
on the second call; tests can ``reset()`` to re-run.

Failure handling: per-bundle errors are caught and recorded so the GUI can
surface them; one bad bundle never blocks boot or other bundles.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import plugin_registry
from .hook_loader import HookBundleSpec, load_bundle

logger = logging.getLogger("eCan")


@dataclass
class _AutoloadError:
    bundle: str
    install_path: str
    message: str
    when: float = field(default_factory=time.time)


_LOCK = threading.Lock()
_INITIALIZED: bool = False
_LOADED: dict[str, list[Any]] = {}  # bundle_name -> [Hook instances]
_ERRORS: list[_AutoloadError] = []


def initialize() -> dict[str, Any]:
    """Warm-load every enabled, user-installed plugin.

    Returns a summary dict::

        {
          "loaded": [ {name, install_path, hook_count} ],
          "skipped": [ {name, reason} ],
          "errors":  [ {bundle, install_path, message} ],
          "already_initialized": bool,
        }
    """
    global _INITIALIZED
    with _LOCK:
        if _INITIALIZED:
            return _summary(already=True)
        _INITIALIZED = True

    loaded_summary: list[dict] = []
    skipped: list[dict] = []
    errors: list[dict] = []

    try:
        installed = plugin_registry.list_installed()
    except Exception as e:
        logger.error(f"[PluginAutoload] failed to read registry: {e}", exc_info=True)
        installed = []

    for entry in installed:
        if not entry.enabled:
            skipped.append({"name": entry.name, "reason": "disabled"})
            continue
        if entry.kind != "hook_bundle":
            skipped.append({"name": entry.name, "reason": f"kind={entry.kind!r} not loaded in Phase 1"})
            continue
        install_path = entry.install_path
        if not install_path or not Path(install_path).is_dir():
            err = _AutoloadError(
                bundle=entry.name,
                install_path=install_path,
                message="install_path missing on disk",
            )
            _ERRORS.append(err)
            errors.append({"bundle": err.bundle, "install_path": err.install_path, "message": err.message})
            logger.warning(f"[PluginAutoload] {entry.name!r}: {err.message}")
            continue

        spec = HookBundleSpec(path=install_path, enabled=True)
        try:
            hooks = load_bundle(spec)
        except Exception as e:
            err = _AutoloadError(
                bundle=entry.name,
                install_path=install_path,
                message=f"{type(e).__name__}: {e}",
            )
            _ERRORS.append(err)
            errors.append({"bundle": err.bundle, "install_path": err.install_path, "message": err.message})
            logger.warning(f"[PluginAutoload] {entry.name!r} load failed: {err.message}")
            continue

        _LOADED[entry.name] = list(hooks)
        loaded_summary.append({
            "name": entry.name,
            "install_path": install_path,
            "hook_count": len(hooks),
        })
        logger.info(
            f"[PluginAutoload] warm-loaded {entry.name!r} "
            f"({len(hooks)} hook(s)) from {install_path}"
        )

    return {
        "loaded": loaded_summary,
        "skipped": skipped,
        "errors": errors,
        "already_initialized": False,
    }


def get_loaded_hooks(bundle: str) -> list[Any]:
    """Return the warm-loaded hook list for a bundle, or [] if not loaded."""
    return list(_LOADED.get(bundle, []))


def get_loaded_bundles() -> list[str]:
    """Return the names of every successfully warm-loaded bundle."""
    return sorted(_LOADED.keys())


def get_autoload_errors() -> list[dict]:
    """Return a copy of the boot-time autoload errors for GUI display."""
    return [
        {"bundle": e.bundle, "install_path": e.install_path,
         "message": e.message, "when": e.when}
        for e in _ERRORS
    ]


def reset() -> None:
    """Test-only: clear state so initialize() can run again."""
    global _INITIALIZED
    with _LOCK:
        _INITIALIZED = False
        _LOADED.clear()
        _ERRORS.clear()


def _summary(*, already: bool) -> dict:
    return {
        "loaded": [
            {"name": n, "install_path": "", "hook_count": len(_LOADED[n])}
            for n in get_loaded_bundles()
        ],
        "skipped": [],
        "errors": get_autoload_errors(),
        "already_initialized": already,
    }


__all__ = [
    "initialize",
    "get_loaded_hooks",
    "get_loaded_bundles",
    "get_autoload_errors",
    "reset",
]
