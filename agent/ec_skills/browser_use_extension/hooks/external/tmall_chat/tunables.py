"""Per-node tunables for the Tmall chat bundle.

Same three-level resolution as ``feige_chat/tunables.py``:

1. Per-node override — ``state["metadata"]["browser_auto_overrides"][<name>]``
2. Global env var — ``ECAN_<NAME>``
3. Hardcoded default

Knob names are Tmall-branded (``TMALL_*``) and stay bundle-side; the
platform only ever sees them through typed bridge methods.
"""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger("eCan")

# Phase 1 defaults — conservative, mirroring Feige's flood-tested values.
DEFAULT_TMALL_TYPING_CONCURRENCY = 1
DEFAULT_TMALL_TAB_RESOLVE_TIMEOUT_S = 5.0
DEFAULT_TMALL_TAB_RESOLVE_CACHE_TTL_S = 10.0
DEFAULT_TMALL_TYPING_LOCK_WAIT_S = 10.0
DEFAULT_TMALL_SEND_CDP_EVALUATE_TIMEOUT_S = 15.0


def _node_override(name: str, state: dict | None) -> Any | None:
    if not state or not isinstance(state, dict):
        return None
    metadata = state.get("metadata")
    if not isinstance(metadata, dict):
        return None
    overrides = metadata.get("browser_auto_overrides")
    if not isinstance(overrides, dict):
        return None
    if name not in overrides:
        return None
    return overrides[name]


def resolve_int(name: str, default: int, state: dict | None = None) -> int:
    override = _node_override(name, state)
    if override is not None:
        try:
            return int(override)
        except (TypeError, ValueError):
            logger.debug(f"[tmall-tunables] invalid node override {name}={override!r}, falling back")
    env_val = os.getenv("ECAN_" + name)
    if env_val:
        try:
            return int(env_val)
        except (TypeError, ValueError):
            logger.debug(f"[tmall-tunables] invalid env ECAN_{name}={env_val!r}, falling back")
    return default


def resolve_float(name: str, default: float, state: dict | None = None) -> float:
    override = _node_override(name, state)
    if override is not None:
        try:
            return float(override)
        except (TypeError, ValueError):
            logger.debug(f"[tmall-tunables] invalid node override {name}={override!r}, falling back")
    env_val = os.getenv("ECAN_" + name)
    if env_val:
        try:
            return float(env_val)
        except (TypeError, ValueError):
            logger.debug(f"[tmall-tunables] invalid env ECAN_{name}={env_val!r}, falling back")
    return default


def _coerce_bool(value: Any) -> "bool | None":
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    s = str(value).strip().lower()
    if s in ("1", "true", "yes", "on"):
        return True
    if s in ("0", "false", "no", "off", ""):
        return False
    return None


def resolve_bool(name: str, default: bool, state: dict | None = None) -> bool:
    coerced = _coerce_bool(_node_override(name, state))
    if coerced is not None:
        return coerced
    coerced = _coerce_bool(os.getenv("ECAN_" + name))
    if coerced is not None:
        return coerced
    return default
