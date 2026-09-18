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


def _find_user_data_dir_by_port(debug_port: int, timeout: float = 30.0) -> str:
    """Read ``--user-data-dir`` off whichever process owns *debug_port*.

    Better than matching the directory name against the vendor's profile id
    (what the AdsPower path does): it does not assume the vendor names the
    directory after the id, and it cannot pick the wrong browser when several
    are open. Used for Ziniao, whose startBrowser hands back the port.
    """
    import psutil

    deadline = time.time() + timeout
    while time.time() < deadline:
        pids = set()
        try:
            for conn in psutil.net_connections(kind="inet"):
                if conn.laddr and conn.laddr.port == int(debug_port) and conn.pid:
                    pids.add(conn.pid)
        except (psutil.AccessDenied, OSError):
            pass

        # The listener may be a parent of the process holding the profile, so
        # walk children too.
        for pid in list(pids):
            try:
                pids.update(c.pid for c in psutil.Process(pid).children(recursive=True))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        for pid in pids:
            try:
                for arg in (psutil.Process(pid).cmdline() or []):
                    if arg.startswith("--user-data-dir="):
                        return arg.split("=", 1)[1]
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        time.sleep(1.0)

    raise RuntimeError(
        f"no process is holding a profile on debugging port {debug_port}; the "
        f"store browser may have failed to start")


def _ziniao_store_record(store_id: str, *, api_url: str, api_port: int,
                         company: str, username: str, password: str,
                         use_socket: bool = False) -> dict:
    """The store's entry from ``getBrowserList``, or {} if it is not listed.

    UNVALIDATED against a live Ziniao install: the list response shape is read
    defensively and a miss is not fatal, because the import only needs the
    store id -- the name and proxy are nice-to-have metadata.
    """
    from agent.mcp.server.ziniao.ziniao import listZiniaoBrowsers

    try:
        result = listZiniaoBrowsers(
            api_url=api_url, api_port=api_port, company=company,
            username=username, password=password, use_socket=use_socket,
        )
    except Exception as exc:
        logger.warning(f"[browser-import] Ziniao getBrowserList failed: {exc}")
        return {}

    # Their payload nests the rows under one of several plausible keys.
    rows = None
    for key in ("data", "list", "browserList", "result"):
        candidate = result.get(key) if isinstance(result, dict) else None
        if isinstance(candidate, list):
            rows = candidate
            break
        if isinstance(candidate, dict):
            for inner in ("list", "browserList", "records"):
                if isinstance(candidate.get(inner), list):
                    rows = candidate[inner]
                    break
            if rows is not None:
                break
    if not rows:
        return {}

    wanted = str(store_id).strip()
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key in ("browserOauth", "browser_oauth", "id", "storeId", "store_id"):
            if str(row.get(key) or "").strip() == wanted:
                return row
    return {}


def import_ziniao(
    vendor_profile_id: str,
    new_id: str,
    *,
    api_url: str = "",
    api_port: int = 0,
    company: str = "",
    username: str = "",
    password: str = "",
    use_socket: bool = False,
    label: str = "",
    fingerprint_profile: str = "",
    browser_path: str = "",
    overwrite: bool = False,
    progress: _Progress = None,
) -> dict:
    """Copy a Ziniao (Ziniao / SuperBrowser) store profile into our registry.

    Same shape as :func:`import_adspower`: start the store briefly so its
    directory appears on a running process, copy it without caches, stop it.
    ``vendor_profile_id`` is the store id Ziniao calls ``browserOauth``.

    **UNVALIDATED.** Written against the local API this repo already drives
    (``agent/mcp/server/ziniao``) but never run against a live Ziniao install.
    Two things are most likely to need adjusting once it is: the shape of the
    ``getBrowserList`` response, and whether the proxy is recoverable at all.

    On the proxy specifically: Ziniao applies the store proxy inside its own
    browser, and if the list response does not expose it, the imported profile
    has NO proxy and will egress from this machine address. The record is still
    written -- a direct profile is a legitimate configuration -- but the caller
    is told, because for an anti-detect identity that difference matters more
    than anything else in the copy.
    """
    from .fingerprint_browser import resolve_browser_path
    from agent.mcp.server.ziniao.ziniao import (
        startZiniaoBrowser, stopZiniaoBrowser,
    )

    if registry.get_profile(new_id) and not overwrite:
        raise ValueError(
            f"'{new_id}' is already registered; pass overwrite to replace it")

    dest = Path(registry.browser_data_root()) / f"{new_id}_{registry.install_salt()}"
    if dest.exists() and not overwrite:
        raise ValueError(f"{dest} already exists; pass overwrite to replace it")

    creds = dict(api_url=api_url, api_port=api_port, company=company,
                 username=username, password=password, use_socket=use_socket)

    _say(progress, f"reading Ziniao store '{vendor_profile_id}'")
    store = _ziniao_store_record(vendor_profile_id, **creds)

    _say(progress, "starting it (its directory is only on the command line)")
    debug_port, _launcher_page, _raw = startZiniaoBrowser(
        browser_oauth=vendor_profile_id, headless=False, **creds)
    try:
        src = Path(_find_user_data_dir_by_port(debug_port))
        _say(progress, f"found {src}")
    finally:
        _say(progress, "stopping it so the copy is consistent")
        stopZiniaoBrowser(browser_oauth=vendor_profile_id, **creds)
        # Chromium writes on the way out; copying through that loses cookies.
        time.sleep(3.0)

    if not src.is_dir():
        raise RuntimeError(f"the vendor's profile directory does not exist: {src}")

    if dest.exists():
        _say(progress, f"replacing {dest}")
        shutil.rmtree(dest)
    size = _copy_profile(src, dest, progress)
    _say(progress, f"copied {size / 1_048_576:.0f} MB")

    # Proxy, if their list response happens to carry one. Field names are a
    # guess -- see the docstring.
    proxy = {}
    proxy_password = ""
    for host_key, port_key, user_key, pass_key, type_key in (
        ("proxyHost", "proxyPort", "proxyUser", "proxyPassword", "proxyType"),
        ("proxy_host", "proxy_port", "proxy_user", "proxy_password", "proxy_type"),
    ):
        if str(store.get(host_key) or "").strip():
            proxy = {
                "scheme": str(store.get(type_key) or "socks5").strip().lower(),
                "host": str(store.get(host_key)).strip(),
                "port": int(store.get(port_key) or 0),
                "username": str(store.get(user_key) or "").strip(),
            }
            proxy_password = str(store.get(pass_key) or "")
            break

    if not proxy:
        logger.warning(
            f"[browser-import] Ziniao store '{vendor_profile_id}' exposed no "
            f"proxy, so '{new_id}' is registered WITHOUT one and will reach "
            f"the site from this machine address. Add the proxy in "
            f"Settings -> Browser Profiles before using it as an identity.")
        _say(progress, "WARNING: no proxy came back from Ziniao -- this profile "
                       "will egress from this machine until you add one")

    resolved_browser = browser_path or resolve_browser_path({})
    record = registry.make_profile(
        new_id,
        label=label or str(store.get("name") or store.get("storeName") or new_id),
        domain_name=str(store.get("domain") or store.get("platform") or ""),
        user_data_dir=str(dest),
        browser_path=resolved_browser,
        browser_version=Path(resolved_browser).parent.parent.name,
        proxy=proxy,
        fingerprint_profile=fingerprint_profile,
        imported_from={
            "vendor": "ziniao",
            "profile_id": vendor_profile_id,
            "source_dir": str(src),
            "imported_at": int(time.time()),
        },
    )
    record = registry.save_profile(record, proxy_password=proxy_password)
    _say(progress, f"registered as '{new_id}'")
    return record
