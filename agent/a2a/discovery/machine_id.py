"""
Stable per-install machine identifier.

Generated once on first launch and persisted under the user's data home at
``<user_data_home>/discovery/machine_id.json``. Survives renames, IP changes,
OS upgrades. Used by zeroconf node records and by the future WAN relay so
peers can address "this physical eCan install" regardless of network topology.

Why not hostname or MAC?
    - Hostnames change (machine renames, hotel WiFi captive-portal sets one).
    - MACs are NIC-bound; laptops have multiple NICs (WiFi + Ethernet + VPN).
    - We need a single stable handle that's ours, not borrowed from the OS.
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Optional

from utils.logger_helper import logger_helper as logger

_MACHINE_ID_FILENAME = "machine_id.json"
_MACHINE_ID_SUBDIR = "discovery"


def _machine_id_path(user_data_home: str | os.PathLike) -> Path:
    return Path(user_data_home) / _MACHINE_ID_SUBDIR / _MACHINE_ID_FILENAME


def get_machine_id(user_data_home: str | os.PathLike) -> str:
    """Return the stable machine_id, generating + persisting on first call.

    Format is a standard UUID4 string (lowercase, dashes), e.g.
    ``7fd4a55d-4aad-4238-9c11-0e6c3a8b9412``. Always 36 chars.

    Failure modes are silent — if the file is unreadable or the directory
    can't be created, returns a fresh UUID (won't persist). Caller behavior
    degrades gracefully: peers see a different ID every restart, but
    discovery still works.
    """
    path = _machine_id_path(user_data_home)
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            mid = str(data.get("machine_id") or "").strip()
            if _looks_like_uuid(mid):
                return mid
            logger.warning(
                f"[discovery.machine_id] {path} present but invalid; regenerating"
            )
    except Exception as e:
        logger.warning(f"[discovery.machine_id] failed to read {path}: {e}; regenerating")

    new_id = str(uuid.uuid4())
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"machine_id": new_id, "version": 1}, indent=2),
            encoding="utf-8",
        )
        logger.info(f"[discovery.machine_id] generated new machine_id={new_id} → {path}")
    except Exception as e:
        logger.warning(
            f"[discovery.machine_id] failed to persist machine_id at {path}: {e}; "
            f"using ephemeral id={new_id} for this run"
        )
    return new_id


def machine_id_short(machine_id: str, n: int = 8) -> str:
    """First N chars of the machine_id (dashes stripped) — for service names."""
    return machine_id.replace("-", "")[:n]


def _looks_like_uuid(s: str) -> bool:
    if not s or len(s) != 36:
        return False
    try:
        uuid.UUID(s)
        return True
    except (ValueError, AttributeError):
        return False


def peek_machine_id(user_data_home: str | os.PathLike) -> Optional[str]:
    """Return the persisted machine_id without generating one if absent."""
    path = _machine_id_path(user_data_home)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        mid = str(data.get("machine_id") or "").strip()
        return mid if _looks_like_uuid(mid) else None
    except Exception:
        return None
