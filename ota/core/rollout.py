#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rollout gating for OTA update checks.

Server side: ``build_system/scripts/set_rollout.py`` writes
``{env}/channels/{channel}/rollout.json`` (see docs/RELEASE_GUIDE.md).
Client side: this module fetches that file once per TTL and answers
"may this client be offered version X?".

Decision order (mirrors the server-side guards in ``set_rollout.plan``):

  1. no file / unreadable / fetch failed     -> allow  (fail open — a
     control-plane outage must never brick update checks)
  2. ``paused=True``                         -> deny   (kill switch, all
     versions, checked before anything else)
  3. ``version`` set and candidate != it     -> allow  (the gate is
     scoped to the version being promoted; older/other candidates pass)
  4. ``user_prefix`` in whitelist -> allow (whitelist wins over percent,
     so percent=0 + whitelist = internal ring)
  5. ``percent >= 100``                      -> allow
  6. ``percent <= 0``                        -> deny
  7. otherwise bucket(sha256(install_id@candidate)) % 100 < percent

The bucket is deterministic per (install_id, version): raising percent
never removes an already-eligible client (monotone), and the same
client keeps its slot across checks (stable).
"""

import hashlib
import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

import requests

from utils.logger_helper import logger_helper as logger

try:
    from config.app_info import app_info
except ImportError:  # pragma: no cover - defensive, OTA must not crash
    app_info = None

from ota.config.loader import ota_config
from .install_state import _atomic_write_text

_INSTALL_ID_FILE_NAME = "ota_install_id.json"
_ROLLOUT_TTL_SECONDS = 300.0
_REQUEST_TIMEOUT = 5.0

_cache_lock = threading.Lock()
# (timestamp of last attempt, data of last resolved value). data=None
# means "resolved open" (404 / unparsable body). A failed transport
# attempt refreshes the attempt clock but keeps the previous data, so a
# control-plane outage degrades to stale-while-error, then to open.
_last_attempt: float = 0.0
_last_data: Optional[Any] = None

# In-memory install id used only when app_info is unavailable (never
# happens in a real build — defensive). Memoized so the bucket slot
# stays stable across checks instead of re-rolling on every call.
_fallback_install_id: Optional[str] = None


def _install_id_file() -> Optional[Path]:
    if app_info is None:
        return None
    try:
        return Path(app_info.appdata_path) / _INSTALL_ID_FILE_NAME
    except Exception:
        return None


def get_install_id() -> str:
    """Return this installation's stable bucket identity.

    Resolution order:
      1. ``ECAN_OTA_INSTALL_ID`` env var — QA hook to pin a bucket.
      2. ``{appdata}/ota_install_id.json`` — generated on first use.
      3. memoized ``uuid4().hex`` (in-memory only; defensive path when
         app_info is unavailable — never happens in a real build).

    A change of install_id re-rolls the client's bucket slot, which is
    acceptable (worst case the client enters/leaves a percent cohort
    one step early/late) — hence best-effort persistence is enough.
    """
    env_id = os.environ.get("ECAN_OTA_INSTALL_ID")
    if env_id:
        return env_id.strip().lower()

    path = _install_id_file()
    if path is not None:
        try:
            if path.exists():
                payload = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(payload, dict):
                    existing = str(payload.get("install_id") or "").strip()
                    if existing:
                        return existing
        except Exception:
            logger.debug("[OTA] install_id file unreadable, regenerating", exc_info=True)
        new_id = uuid.uuid4().hex
        try:
            _atomic_write_text(
                path,
                json.dumps(
                    {"install_id": new_id, "created_at": int(time.time())},
                    ensure_ascii=False,
                    indent=2,
                ),
            )
        except Exception:
            logger.debug("[OTA] failed to persist install_id", exc_info=True)
        return new_id

    global _fallback_install_id
    if _fallback_install_id is None:
        _fallback_install_id = uuid.uuid4().hex
    return _fallback_install_id


def _normalize_version(value: Any) -> str:
    """Lower-case, trim, drop a leading ``v`` — nothing smarter.

    Both sides of the comparison (rollout.json written by
    set_rollout.py, latest_version from the appcast) are already
    normalized to bare versions; this just absorbs cosmetic drift.
    """
    s = str(value or "").strip().lower()
    if s.startswith("v") and len(s) > 1:
        s = s[1:]
    return s


def bucket_for(install_id: str, version: str) -> int:
    """Deterministic 0..99 slot for (install_id, version)."""
    digest = hashlib.sha256(f"{install_id}@{version}".encode("utf-8")).hexdigest()
    return int(digest, 16) % 100


def is_eligible(
    rollout: Optional[Dict[str, Any]],
    version: str,
    install_id: str,
    user_prefix: Optional[str] = None,
) -> bool:
    """Apply the rollout decision table to one candidate version.

    ``rollout`` is the parsed rollout.json (or None — treated as fully
    open). ``version`` is the candidate being offered. ``user_prefix``
    is the per-user whitelist key (email local-part, lower-cased).

    Pure function: no I/O, no cache — safe to call from tests directly.
    """
    if not isinstance(rollout, dict):
        return True

    if bool(rollout.get("paused")):
        return False

    rollout_version = _normalize_version(rollout.get("version"))
    candidate = _normalize_version(version)
    if rollout_version and candidate and rollout_version != candidate:
        # Gate only governs the version it names; anything else
        # (older candidates, other channels' builds) passes untouched.
        return True
    if rollout_version and not candidate:
        # No version to compare against — fail open rather than
        # silently withholding an unnameable candidate.
        return True

    try:
        percent = int(rollout.get("percent", 100))
    except (TypeError, ValueError):
        percent = 100

    cohort = rollout.get("cohort_include_prefix") or []
    if user_prefix:
        prefix = str(user_prefix).strip().lower()
        if prefix and prefix in {str(c).strip().lower() for c in cohort}:
            return True

    if percent >= 100:
        return True
    if percent <= 0:
        return False

    if not install_id:
        # Can't bucket without an identity — fail open (matches the
        # "control plane unavailable = open" rule).
        return True
    return bucket_for(install_id, candidate) < percent


def fetch_rollout(timeout: float = _REQUEST_TIMEOUT, force: bool = False) -> Optional[Dict[str, Any]]:
    """Fetch rollout.json with a TTL cache. None = treat as open.

    Caching rules (all fail-open by construction):
      * resolved value (success/404/unparsable) cached for 300s;
      * transport error within TTL returns the last resolved value;
      * transport error after TTL keeps stale data (stale-while-error)
        and only degrades to None if nothing was ever resolved;
      * any unexpected exception inside becomes None (open).
    """
    global _last_attempt, _last_data

    now = time.time()
    with _cache_lock:
        if not force and (now - _last_attempt) < _ROLLOUT_TTL_SECONDS:
            return _last_data

        try:
            url = ota_config.get_rollout_url()
        except Exception:
            url = ""
        if not url:
            # OTA disabled / no config — nothing to gate on.
            return None

        try:
            response = requests.get(
                url,
                timeout=timeout,
                headers={"Cache-Control": "no-cache", "Pragma": "no-cache"},
            )
            if response.status_code == 404:
                # File absent = no rollout record = fully open.
                _last_attempt = now
                _last_data = None
                return None
            response.raise_for_status()
            parsed = json.loads(response.content.decode("utf-8"))
            if not isinstance(parsed, dict):
                raise ValueError(f"rollout.json is not an object: {type(parsed)!r}")
            _last_attempt = now
            _last_data = parsed
            return parsed
        except Exception as exc:
            _last_attempt = now
            if isinstance(exc, (json.JSONDecodeError, ValueError, UnicodeDecodeError)):
                # Unparsable body = "resolved open" (fail-open).
                _last_data = None
                logger.warning(f"[OTA] rollout.json unusable ({exc}); treating as open")
                return None
            logger.info(
                f"[OTA] rollout.json fetch failed ({exc}); "
                f"{'serving cached value' if _last_data is not None else 'failing open'}"
            )
            return _last_data
