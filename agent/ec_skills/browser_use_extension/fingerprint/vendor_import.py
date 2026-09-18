"""Import a logged-in profile out of an anti-detect vendor and into our registry.

This automates the migration that was first done by hand. The awkward part is
step 2: **a vendor profile's real configuration exists only on the running
browser's command line.** The vendor's app data holds their Electron app and
browser binaries, not the profiles, and their API will not tell you where the
user-data-dir is. So the only way to find it is to start the profile, read the
command line off the process, and stop it again.

    vendor API  ->  name, domain, PROXY CREDENTIALS (not on the command line)
    process     ->  --user-data-dir (not in the API)
    both        ->  one registry record

The copy excludes caches: ~762MB as-is against ~20MB without them, which is the
difference between a profile that can be synced to a bucket and one that cannot.

Two things are deliberately NOT copied from the vendor:

* **Their browser binary.** It is a patched Chromium that understands their
  fingerprint blob, and we cannot drive it. We record ours instead, pinned at
  import time -- a profile written by a newer Chromium cannot be opened by an
  older one, so the binary is part of the profile.
* **Their fingerprint.** It lives in an opaque ``--extended-parameters`` blob
  that only their browser can read. Ours is stealth JS, named separately on the
  record.
"""

import shutil
import time
from pathlib import Path
from typing import Callable, Optional

from utils.logger_helper import logger_helper as logger

from . import profile_registry as registry
from .profile_registry import PRUNABLE_DIRS

# Runtime state that must not travel: a copied lock or port file makes the new
# profile look like it is already open somewhere.
_SKIP_FILES = ("SingletonLock", "SingletonCookie", "SingletonSocket",
               "DevToolsActivePort", "lockfile", ".ecan_cdp.json")

_Progress = Optional[Callable[[str], None]]


def _say(progress: _Progress, msg: str) -> None:
    logger.info(f"[browser-import] {msg}")
    if progress:
        progress(msg)


def _vendor_record(vendor_profile_id: str, api_key: str, api_port: int,
                   api_url: str) -> dict:
    """Name, domain and proxy credentials, straight from the vendor's local API."""
    import json
    import urllib.request

    base = (api_url or "http://local.adspower.net").rstrip("/")
    if ":" not in base.split("//", 1)[-1]:
        base = f"{base}:{api_port}"
    url = f"{base}/api/v1/user/list?user_id={vendor_profile_id}"
    req = urllib.request.Request(url)
    if api_key:
        req.add_header("Authorization", f"Bearer {api_key}")
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.load(r)
    if data.get("code") != 0:
        raise RuntimeError(f"AdsPower API refused the lookup: {data.get('msg')}")
    items = (data.get("data") or {}).get("list") or []
    if not items:
        raise RuntimeError(
            f"AdsPower has no profile '{vendor_profile_id}' (check the id in "
            f"their profile list -- it is the short serial, not the name)")
    return items[0]


def _find_user_data_dir(vendor_profile_id: str, timeout: float = 30.0) -> str:
    """Read ``--user-data-dir`` off the running vendor browser's command line.

    The vendor names the directory after the profile id, and the browser is not
    necessarily called ``chrome.exe`` (AdsPower ships ``SunBrowser.exe``), so we
    match on the argument rather than on the process name.
    """
    import psutil

    deadline = time.time() + timeout
    while time.time() < deadline:
        for proc in psutil.process_iter(["cmdline"]):
            try:
                for arg in (proc.info.get("cmdline") or []):
                    if arg.startswith("--user-data-dir=") and vendor_profile_id in arg:
                        return arg.split("=", 1)[1]
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        time.sleep(1.0)
    raise RuntimeError(
        f"could not find a running browser holding profile '{vendor_profile_id}'. "
        f"It may have failed to start -- try opening it in AdsPower first.")


def _copy_profile(src: Path, dest: Path, progress: _Progress) -> int:
    """Copy the profile without its caches. Returns the bytes copied."""
    copied = [0]

    def _ignore(directory, names):
        skip = set()
        for n in names:
            full = Path(directory) / n
            if n in _SKIP_FILES:
                skip.add(n)
            elif full.is_dir() and n in PRUNABLE_DIRS:
                skip.add(n)
        return skip

    def _copy2(s, d):
        try:
            copied[0] += Path(s).stat().st_size
        except OSError:
            pass
        shutil.copy2(s, d)

    _say(progress, f"copying {src} -> {dest} (caches excluded)")
    shutil.copytree(src, dest, ignore=_ignore, copy_function=_copy2,
                    dirs_exist_ok=False)
    return copied[0]


def import_adspower(
    vendor_profile_id: str,
    new_id: str,
    *,
    api_key: str = "",
    api_port: int = 50325,
    api_url: str = "",
    label: str = "",
    fingerprint_profile: str = "",
    browser_path: str = "",
    overwrite: bool = False,
    progress: _Progress = None,
) -> dict:
    """Copy an AdsPower profile into our registry and return the new record.

    Starts the vendor profile (to learn its directory) and stops it again --
    if it was already open, it will be closed.
    """
    from .fingerprint_browser import resolve_browser_path

    if registry.get_profile(new_id) and not overwrite:
        raise ValueError(
            f"'{new_id}' is already registered; pass overwrite to replace it")

    dest = Path(registry.browser_data_root()) / f"{new_id}_{registry.install_salt()}"
    if dest.exists() and not overwrite:
        raise ValueError(f"{dest} already exists; pass overwrite to replace it")

    _say(progress, f"reading AdsPower profile '{vendor_profile_id}'")
    vendor = _vendor_record(vendor_profile_id, api_key, api_port, api_url)
    proxy_cfg = vendor.get("user_proxy_config") or {}

    from agent.mcp.server.ads_power.ads_power import (
        startAdspowerProfile, stopAdspowerProfile,
    )

    _say(progress, "starting it (its directory is only on the command line)")
    startAdspowerProfile(api_key, vendor_profile_id, api_port, base_url=api_url or None)
    try:
        src = Path(_find_user_data_dir(vendor_profile_id))
        _say(progress, f"found {src}")
    finally:
        _say(progress, "stopping it so the copy is consistent")
        try:
            stopAdspowerProfile(api_key, vendor_profile_id, api_port)
        except Exception as exc:
            logger.warning(f"[browser-import] could not stop the vendor profile: {exc}")
        # Chromium writes on the way out; copying through that loses cookies.
        time.sleep(3.0)

    if not src.is_dir():
        raise RuntimeError(f"the vendor's profile directory does not exist: {src}")

    if dest.exists():
        _say(progress, f"replacing {dest}")
        shutil.rmtree(dest)
    size = _copy_profile(src, dest, progress)
    _say(progress, f"copied {size / 1_048_576:.0f} MB")

    resolved_browser = browser_path or resolve_browser_path({})
    record = registry.make_profile(
        new_id,
        label=label or vendor.get("name") or new_id,
        domain_name=vendor.get("domain_name") or "",
        user_data_dir=str(dest),
        browser_path=resolved_browser,
        browser_version=Path(resolved_browser).parent.parent.name,
        proxy={
            "scheme": proxy_cfg.get("proxy_type") or "socks5",
            "host": proxy_cfg.get("proxy_host") or "",
            "port": int(proxy_cfg.get("proxy_port") or 0),
            "username": proxy_cfg.get("proxy_user") or "",
        },
        fingerprint_profile=fingerprint_profile,
        imported_from={
            "vendor": "adspower",
            "profile_id": vendor_profile_id,
            "source_dir": str(src),
            "imported_at": int(time.time()),
        },
    )
    record = registry.save_profile(record,
                                   proxy_password=proxy_cfg.get("proxy_password") or "")
    _say(progress, f"registered as '{new_id}'")
    return record
