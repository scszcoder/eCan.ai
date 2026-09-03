"""OS-native machine fingerprint for vehicle affinity.

Design + rationale: docs/VEHICLE_AFFINITY_MACHINE_ID.md.

The vehicle-affinity gate needs the app and the Fast-Deploy CLI subprocess
to compute the SAME id for the same physical machine. The old per-user
``machine_id.json`` random UUID was file-path-derived, so a data-home
mismatch between the two paths produced two different ids and the gate
skipped every agent (2026-09-03 customer incident).

This module derives the id from the OS's own per-install identifier —
NOT NIC-based (multi-NIC is a non-issue) and read identically by any
process regardless of data-home path:

    Windows : HKLM\\SOFTWARE\\Microsoft\\Cryptography\\MachineGuid
    macOS   : IOPlatformUUID (ioreg)
    Linux   : /etc/machine-id (or /var/lib/dbus/machine-id)

The raw value is hashed into a deterministic UUID5 (privacy + drop-in
UUID format). Callers fall back to the persisted random UUID
(machine_id.py) when the OS id can't be read.

Lives next to vehicle_affinity (not under agent/a2a/discovery/) so importing
it never triggers that package's eager zeroconf import — zeroconf is
desktop-only (commented out in requirements-worker/web), and the machine
fingerprint must resolve in any environment.

Pure stdlib; safe for cloud workers.
"""

from __future__ import annotations

import platform
import subprocess
import uuid
from typing import Optional

from utils.logger_helper import logger_helper as logger

# Stable namespace for eCan machine ids — do not change (would shift every id).
ECAN_MACHINE_NS = uuid.UUID("6b3f9d2e-8c4a-5f17-b0e6-2a1c7d9e4f83")


def _read_windows_machine_guid() -> str:
    try:
        import winreg
        with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Cryptography",
                0,
                winreg.KEY_READ | getattr(winreg, "KEY_WOW64_64KEY", 0)) as key:
            val, _ = winreg.QueryValueEx(key, "MachineGuid")
            return str(val or "").strip()
    except Exception as e:
        logger.debug(f"[machine_fingerprint] MachineGuid read failed: {e}")
        return ""


def _read_macos_platform_uuid() -> str:
    try:
        out = subprocess.run(
            ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
            capture_output=True, text=True, timeout=8)
        for line in (out.stdout or "").splitlines():
            if "IOPlatformUUID" in line:
                # …"IOPlatformUUID" = "XXXXXXXX-...."
                parts = line.split("=", 1)
                if len(parts) == 2:
                    return parts[1].strip().strip('"').strip()
    except Exception as e:
        logger.debug(f"[machine_fingerprint] IOPlatformUUID read failed: {e}")
    return ""


def _read_linux_machine_id() -> str:
    for path in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                mid = fh.read().strip()
                if mid:
                    return mid
        except Exception:
            continue
    return ""


def read_os_machine_id() -> str:
    """Raw OS-native install id for this platform, or '' if unavailable."""
    system = platform.system()
    if system == "Windows":
        return _read_windows_machine_guid()
    if system == "Darwin":
        return _read_macos_platform_uuid()
    return _read_linux_machine_id()


def get_os_vehicle_id() -> Optional[str]:
    """Deterministic UUID5 of the OS machine id, or None when unavailable.

    Same physical machine -> same value, in any process, regardless of the
    user-data-home path. None signals the caller to use the persisted-UUID
    fallback (machine_id.py).
    """
    raw = read_os_machine_id()
    if not raw:
        return None
    try:
        return str(uuid.uuid5(ECAN_MACHINE_NS, raw))
    except Exception as e:
        logger.debug(f"[machine_fingerprint] uuid5 normalize failed: {e}")
        return None
