"""Vehicle (host) affinity for agent startup.

Phase 1.5 of docs/SHARED_SKILL_MULTI_TASK_PLAN.md: when one user account is
logged in on multiple host computers, cloud sync gives every host the same
agents and tasks, and every host used to start worker loops for ALL of them —
so schedule-triggered tasks double-fired. Each host is modeled as a
"vehicle" (``DBAgentVehicle``); an agent with a non-empty ``vehicle_id``
only starts on the host whose local vehicle id matches.

The local vehicle id IS the persistent discovery machine_id
(``agent/a2a/discovery/machine_id.py``) — stable per install, survives
renames and IP changes — so matching needs no lookup table.

Back-compat / safety:
- Agents with an empty ``vehicle_id`` start everywhere (today's behaviour);
  single-host users see no change.
- Every failure path fails OPEN (agent starts) — affinity must never brick
  startup.
- Kill switch: ``ECAN_DISABLE_VEHICLE_AFFINITY=1`` disables the gate.
"""

from __future__ import annotations

import os
import platform as _platform
import socket
import threading

from utils.logger_helper import logger_helper as logger

_lock = threading.Lock()
_local_vehicle_id: "str | None" = None   # resolved once per process
_vehicle_registered = False


def _affinity_disabled() -> bool:
    return str(os.getenv("ECAN_DISABLE_VEHICLE_AFFINITY", "")).strip().lower() in (
        "1", "true", "yes", "on"
    )


def _derive_user_data_home(username: str) -> str:
    """Mirror MainGUI's per-user data-home derivation for callers without a
    mainwin (CLI): ``{app_info.appdata_path}/{local}_{domain with . → _}``.

    NOTE: for CN WeChat logins MainGUI's ``self.user`` carries a synthetic
    ``@local`` suffix that a CLI username may not, so the CLI-derived path
    (and hence machine_id) can differ there — prefer the explicit id from
    ``ecan vehicles list`` (the app registers its own row) in that case.
    """
    from config.envi import getECBotDataHome

    local_part, _, domain = (username or "unknown@local").partition("@")
    domain = domain or "local"
    log_user = f"{local_part}_{domain.replace('.', '_')}"
    return f"{getECBotDataHome()}/{log_user}"


def resolve_local_vehicle_id(mainwin=None, username: str = "") -> str:
    """Return this host's vehicle id (= discovery machine_id), or "" on failure.

    The machine_id file lives under the per-user data home; pass either a
    mainwin (app runtime) or a username (CLI). Cached per process after the
    first successful resolution.
    """
    global _local_vehicle_id
    if _local_vehicle_id:
        return _local_vehicle_id
    with _lock:
        if _local_vehicle_id:
            return _local_vehicle_id
        try:
            # Import from the submodule (not the package) — the package
            # __init__ pulls in zeroconf, which cloud/CI environments may
            # not have; machine_id itself is dependency-free.
            from agent.a2a.discovery.machine_id import get_machine_id

            data_home = getattr(mainwin, "my_ecb_data_homepath", "") or ""
            if not data_home and username:
                data_home = _derive_user_data_home(username)
            if not data_home:
                return ""
            mid = get_machine_id(data_home)
            if mid:
                _local_vehicle_id = str(mid)
                return _local_vehicle_id
        except Exception as e:
            logger.warning(f"[VehicleAffinity] local vehicle id resolution failed: {e}")
    return ""


def register_local_vehicle(mainwin) -> None:
    """Upsert this host's DBAgentVehicle row (id = machine_id). Idempotent,
    once per process; every failure is non-fatal."""
    global _vehicle_registered
    if _vehicle_registered:
        return
    try:
        vehicle_id = resolve_local_vehicle_id(mainwin)
        if not vehicle_id:
            return
        service = getattr(getattr(mainwin, "ec_db_mgr", None), "vehicle_service", None)
        if service is None:
            return

        owner = ""
        try:
            from agent.cloud_api.cloud_api import normalize_cloud_owner

            owner = normalize_cloud_owner(getattr(mainwin, "user", "") or "")
        except Exception:
            owner = str(getattr(mainwin, "user", "") or "")

        hostname = ""
        try:
            hostname = socket.gethostname() or ""
        except Exception:
            pass

        existing = None
        try:
            existing = _get_vehicle_row(service, vehicle_id)
        except Exception:
            existing = None

        if existing:
            service.update_vehicle(vehicle_id, {"status": "online", "hostname": hostname})
        else:
            service.add_vehicle({
                "id": vehicle_id,
                "name": hostname or f"vehicle-{vehicle_id[:8]}",
                "owner": owner,
                "vehicle_type": "desktop",
                "platform": _platform.system().lower(),
                "hostname": hostname,
                "status": "online",
            })
            logger.info(
                f"[VehicleAffinity] registered local vehicle id={vehicle_id[:8]}.. "
                f"hostname={hostname}"
            )
        _vehicle_registered = True
    except Exception as e:
        logger.warning(f"[VehicleAffinity] local vehicle registration failed (non-fatal): {e}")


def _get_vehicle_row(service, vehicle_id: str):
    """Fetch one vehicle row dict via DBVehicleService.query_vehicles.

    (There is no ``get_vehicle_by_id`` on the service — calling it raised
    AttributeError, which broke BOTH the registration existence-check and
    the legacy-row hostname fallback: v0.9.95t customer log
    "'DBVehicleService' object has no attribute 'get_vehicle_by_id'".)
    """
    result = service.query_vehicles(id=vehicle_id)
    rows = result.get("data") if isinstance(result, dict) and result.get("success") else None
    if isinstance(rows, list) and rows:
        row = rows[0]
        return row if isinstance(row, dict) else None
    return None


def _vehicle_row_is_local(mainwin, vehicle_id: str) -> bool:
    """True when the DB vehicle row *vehicle_id* describes THIS machine.

    The GUI's vehicle dropdown historically lists legacy LAN-discovery
    vehicle rows (auto-generated ids, name '<hostname>:<os>'), while the
    affinity gate keys on the discovery machine_id row — two id schemes for
    the same physical machine. An assignment made through the GUI must
    still count as local, so fall back to matching the row's hostname/name
    against this host. A lookup failure returns False (an explicit
    assignment that cannot be verified stays non-local — the user
    deliberately assigned somewhere).
    """
    try:
        service = getattr(getattr(mainwin, "ec_db_mgr", None), "vehicle_service", None)
        if service is None:
            return False
        row = _get_vehicle_row(service, vehicle_id)
        if not isinstance(row, dict):
            return False
        local_host = ""
        try:
            local_host = (socket.gethostname() or "").strip().lower()
        except Exception:
            return False
        if not local_host:
            return False
        row_host = str(row.get("hostname") or "").strip().lower()
        row_name = str(row.get("name") or "").strip().lower()
        return bool(
            (row_host and row_host == local_host)
            or row_name == local_host
            or row_name.startswith(f"{local_host}:")
        )
    except Exception as e:
        logger.warning(f"[VehicleAffinity] legacy vehicle-row lookup failed for {vehicle_id[:12]}..: {e}")
        return False


def agent_launch_allowed(agent) -> "tuple[bool, str]":
    """Decide whether *agent* may start on this host.

    Returns (allowed, reason). Reasons: "affinity-disabled", "no-affinity"
    (empty vehicle_id — starts everywhere, back-compat), "local",
    "local-legacy-row" (assigned to a legacy GUI vehicle row that describes
    this machine), "local-vehicle-unresolved" (fail-open), or a skip
    explanation.
    """
    try:
        if _affinity_disabled():
            return True, "affinity-disabled"

        vid = getattr(agent, "vehicle_id", None) or getattr(agent, "vehicle", None)
        vid = str(vid).strip() if vid else ""
        if not vid:
            return True, "no-affinity"

        mainwin = getattr(agent, "mainwin", None)
        local = resolve_local_vehicle_id(mainwin)
        if not local:
            return True, "local-vehicle-unresolved"
        if vid == local:
            return True, "local"
        if _vehicle_row_is_local(mainwin, vid):
            return True, "local-legacy-row"
        return False, f"assigned to vehicle {vid[:12]}.., local vehicle is {local[:12]}.."
    except Exception as e:
        logger.warning(f"[VehicleAffinity] gate check failed (fail-open): {e}")
        return True, "gate-error"


def _reset_for_tests() -> None:
    """Test helper — drop process-level caches."""
    global _local_vehicle_id, _vehicle_registered
    with _lock:
        _local_vehicle_id = None
        _vehicle_registered = False
