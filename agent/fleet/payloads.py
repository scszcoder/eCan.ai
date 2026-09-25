"""What a transfer carries: a window of run logs, or one store's whole login.

A login bundle is everything that makes the new machine look like the same
device to the site (docs/FLEET_TRANSFER_DESIGN.md §1): the registry record
(fingerprint + proxy), the proxy password, the cookies read out over CDP, and
the profile folder without caches and without the files the OS encrypts to
this machine.
"""

from __future__ import annotations

import json
import os
import shutil
import time
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Optional

from utils.logger_helper import logger_helper as logger

BUNDLE_VERSION = 1

# Encrypted to THIS OS account (DPAPI / Keychain): unreadable anywhere else, and
# Local State holds the wrapped key itself -- the receiver's browser makes a new one.
_OS_BOUND_PREFIXES = ("Cookies", "Login Data", "Web Data", "Safe Browsing Cookies")
_OS_BOUND_FILES = ("Local State",)

# Machine-specific or derived from where the record lives.
_LOCAL_ONLY_KEYS = ("user_data_dir", "install_salt", "machine_id", "moved_to")


class PayloadError(RuntimeError):
    pass


# ── logs ─────────────────────────────────────────────────────────────

def build_logs(dest_zip: str, hours: float = 24.0) -> Dict[str, Any]:
    """Zip this machine's run logs changed in the last *hours*."""
    from config.app_info import app_info
    from gui.ipc.w2p_handlers.debug_log_handler import _add_runlogs_dir
    runlogs = Path(app_info.appdata_path) / "runlogs"
    since = time.time() - max(float(hours or 24), 0.1) * 3600
    with zipfile.ZipFile(dest_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        stats = _add_runlogs_dir(zf, runlogs, newer_than=since)
    return {"files": stats["added"], "bytes": stats["bytes"]}


# ── a store's login ──────────────────────────────────────────────────

def _registry():
    from agent.ec_skills.browser_use_extension.fingerprint import profile_registry
    return profile_registry


def _browser():
    from agent.ec_skills.browser_use_extension.fingerprint import fingerprint_browser
    return fingerprint_browser


def _travels(name: str) -> bool:
    if name in _OS_BOUND_FILES:
        return False
    return not any(name.startswith(p) for p in _OS_BOUND_PREFIXES)


def _read_cookies_and_close(profile_id: str) -> list:
    """Cookies of the profile's browser, which is left closed (flushed) afterwards.

    A browser that is not running is started just long enough to read them --
    through its own proxy, the way it always runs.
    """
    from agent.fleet.cookies import get_cookies
    fb = _browser()
    st = fb.profile_status(profile_id)
    started_here = False
    if not st.get("running"):
        fb.launch_profile(profile_id, headless=True)
        st = fb.profile_status(profile_id)
        started_here = True
    if not st.get("running"):
        raise PayloadError(f"could not open login '{profile_id}' to read its cookies")
    cookies = get_cookies(st["cdp_url"])
    fb.close_profile(profile_id)
    if fb.profile_status(profile_id).get("running"):
        raise PayloadError(f"login '{profile_id}' is still open (started "
                           f"{'here' if started_here else 'by another process'}); close it and retry")
    return cookies


def build_profile(profile_id: str, dest_zip: str) -> Dict[str, Any]:
    """Pack one login. Closes its browser (so the session is flushed) first."""
    reg = _registry()
    rec = reg.get_profile(profile_id)
    if not rec:
        raise PayloadError(f"no login '{profile_id}' on this machine")
    src = Path(rec.get("user_data_dir") or "")
    if not src.is_dir():
        raise PayloadError(f"login '{profile_id}' has no folder at {src}")
    cookies = _read_cookies_and_close(profile_id)

    from agent.ec_skills.browser_use_extension.fingerprint.vendor_import import _SKIP_FILES
    manifest = {
        "version": BUNDLE_VERSION,
        "profile": {k: v for k, v in rec.items() if k not in _LOCAL_ONLY_KEYS},
        "proxy_password": reg.get_proxy_password(rec),
        "cookies": len(cookies),
    }
    files = 0
    with zipfile.ZipFile(dest_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))
        zf.writestr("cookies.json", json.dumps(cookies, ensure_ascii=False))
        for root, dirs, names in os.walk(src):
            dirs[:] = [d for d in dirs if d not in reg.PRUNABLE_DIRS]
            for n in names:
                if n in _SKIP_FILES or not _travels(n):
                    continue
                full = Path(root) / n
                try:
                    zf.write(full, "files/" + full.relative_to(src).as_posix())
                    files += 1
                except OSError as exc:
                    logger.warning(f"[fleet] skipped {full.name}: {exc}")
    return {"files": files, "cookies": len(cookies)}


def _safe_member(name: str) -> Optional[PurePosixPath]:
    p = PurePosixPath(name)
    if p.is_absolute() or ".." in p.parts or not p.parts or p.parts[0] != "files" or len(p.parts) < 2:
        return None
    return PurePosixPath(*p.parts[1:])


def install_profile(bundle_zip: str, *, machine_id: str = "", store_id: str = "") -> Dict[str, Any]:
    """Install a login bundle here: record, keyring password, files, pending cookies."""
    from agent.fleet.cookies import PENDING_FILE
    reg = _registry()
    with zipfile.ZipFile(bundle_zip) as zf:
        manifest = json.loads(zf.read("manifest.json"))
        if manifest.get("version") != BUNDLE_VERSION:
            raise PayloadError(f"unsupported login bundle version {manifest.get('version')}")
        record = dict(manifest.get("profile") or {})
        pid = str(record.get("id") or "").strip()
        if not pid:
            raise PayloadError("login bundle has no profile id")
        if _browser().profile_status(pid).get("running"):
            raise PayloadError(f"login '{pid}' is open on this machine; close it first")

        fresh = reg.make_profile(pid)
        dest = Path(fresh["user_data_dir"])
        if dest.exists():
            aside = dest.with_name(f"{dest.name}.before-{int(time.time())}")
            dest.rename(aside)
            logger.info(f"[fleet] kept the previous copy of '{pid}' at {aside}")
        dest.mkdir(parents=True)
        for info in zf.infolist():
            rel = _safe_member(info.filename)
            if rel is None or info.is_dir():
                continue
            target = dest.joinpath(*rel.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as fin, open(target, "wb") as fout:
                shutil.copyfileobj(fin, fout)
        (dest / PENDING_FILE).write_bytes(zf.read("cookies.json"))

    proxy = dict(record.get("proxy") or {})
    proxy.pop("password_ref", None)       # pointed at the SOURCE's keyring
    proxy.pop("password", None)
    record.update({"proxy": proxy, "user_data_dir": str(dest),
                   "install_salt": fresh["install_salt"], "machine_id": machine_id})
    if store_id:
        record["store_id"] = store_id
    reg.save_profile(record, proxy_password=str(manifest.get("proxy_password") or ""))
    return {"profile_id": pid, "cookies": int(manifest.get("cookies") or 0)}


def mark_moved(profile_id: str, to_vehicle_id: str) -> None:
    """Label the source's copy: kept, but it must not run while the other machine holds it."""
    reg = _registry()
    rec = reg.get_profile(profile_id)
    if rec:
        rec = dict(rec)
        rec["moved_to"] = to_vehicle_id
        rec["login_detail"] = f"moved to {to_vehicle_id} at {time.strftime('%Y-%m-%d %H:%M')}"
        reg.save_profile(rec)
