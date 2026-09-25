"""Registry of browser profiles: identity -> user-data-dir + proxy + fingerprint.

A *browser profile* here is one logged-in identity on one site — "the Etsy
store", "the eBay seller account". It binds together the four things that have
to travel as a unit and, until now, did not:

    user_data_dir      the session itself (cookies, history, localStorage)
    proxy              the egress the site has seen this identity use
    fingerprint        which stealth profile to inject
    browser            WHICH binary and version wrote the profile

Session persistence was never the missing piece — Chromium writes to
``--user-data-dir`` and survives a reboot by construction. What was missing was
a record saying those four belong together, so an agent could launch the set.

**This data is local by default and does not go to the cloud.** A profile is a
live logged-in session for a real store account plus the proxy credentials it
egresses through; losing one means someone else can act as that seller. Nothing
here is synced, shared with a skill, or packed into an image, and
``tests/unit/test_browser_profile_stays_local.py`` fails if cloud-bound code
starts referencing it. A profile reaches the cloud only when the user commands
it for that one profile, having been warned what leaves the machine — see
``docs/OWN_FINGERPRINT_BROWSER.md``.

Storage decisions, and why:

* **The password is in ``keyring``, never in the JSON.** The record holds a
  reference. This mirrors how ``auth_manager`` stores refresh tokens and keeps
  the registry file safe to read, back up, and paste into a bug report.
* **A separate file from ``browser_use_settings.json``.** That one is app
  settings the Settings page rewrites wholesale; profiles are data with a
  different lifetime and a different blast radius.
* **A short root path outside AppData** (``BROWSER_DATA_ROOT``). Chromium
  profile directories get deep and Windows MAX_PATH bites; it also keeps
  hundreds of MB of cache out of roaming profiles and backups. This is the one
  convention that is painful to retrofit once profiles exist.

Design notes live in the eCan_lambda repo,
``docs/OWN_FINGERPRINT_BROWSER_PLAN.md``.
"""

import json
import os
import platform
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from utils.logger_helper import logger_helper as logger

# Keyring service name for proxy passwords. One entry per profile id.
_KEYRING_SERVICE = "ecan_browser_proxy"

# Cache subdirectories that are pure derived data. Excluded when a profile is
# copied or packed: ~762MB raw versus ~20MB without them, which is the
# difference between a viable cloud sync and an unviable one.
PRUNABLE_DIRS = (
    "Cache", "Code Cache", "GPUCache", "DawnCache", "DawnGraphiteCache",
    "DawnWebGPUCache", "ShaderCache", "GrShaderCache", "GraphiteDawnCache",
    "Crashpad", "component_crx_cache", "optimization_guide_model_store",
    "Service Worker",
)


def browser_data_root() -> Path:
    """Root for per-profile Chromium user-data directories.

    Deliberately short and outside AppData — see the module docstring. Override
    with ``ECAN_BROWSER_DATA_ROOT`` for tests or a non-default drive.
    """
    override = os.getenv("ECAN_BROWSER_DATA_ROOT")
    if override:
        return Path(override)
    if platform.system() == "Windows":
        return Path("C:/ecan_browser_data")
    return Path.home() / ".ecan" / "browser_data"


def _registry_path() -> Path:
    """Where the registry file lives (user-writable app data)."""
    try:
        from config.app_info import app_info
        base = Path(app_info.appdata_path)
    except Exception:
        base = Path.home() / ".ecan"
    base.mkdir(parents=True, exist_ok=True)
    return base / "browser_profiles.json"


def install_salt() -> str:
    """A stable per-install id, mixed into profile directory names.

    Lets two installs on one machine hold profiles with the same id without
    colliding — the convention the anti-detect vendors use
    (``<profile_id>_<salt>``).
    """
    reg = _load_raw()
    salt = reg.get("install_salt")
    if not salt:
        salt = uuid.uuid4().hex[:6]
        reg["install_salt"] = salt
        _save_raw(reg)
    return salt


def _load_raw() -> dict:
    p = _registry_path()
    if not p.exists():
        return {"install_salt": "", "profiles": []}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("registry root is not an object")
        data.setdefault("profiles", [])
        return data
    except Exception as exc:
        # Never lose a registry to a parse error: move it aside so the next
        # save starts clean and the broken file can still be inspected.
        broken = p.with_suffix(f".broken-{uuid.uuid4().hex[:6]}.json")
        try:
            p.rename(broken)
            logger.error(
                f"[browser-registry] {p.name} is unreadable ({exc}); "
                f"moved to {broken.name} and starting a fresh registry"
            )
        except Exception:
            logger.error(f"[browser-registry] {p.name} is unreadable ({exc})")
        return {"install_salt": "", "profiles": []}


def _save_raw(data: dict) -> None:
    p = _registry_path()
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)  # atomic on the same volume


def list_profiles() -> list[dict]:
    """Every registered profile. Passwords are NOT included."""
    return list(_load_raw().get("profiles") or [])


def get_profile(profile_id: str) -> Optional[dict]:
    for prof in list_profiles():
        if str(prof.get("id")) == str(profile_id):
            return prof
    return None


def save_profile(profile: dict, proxy_password: str = "") -> dict:
    """Insert or replace a profile. The password goes to the keyring only.

    ``proxy_password`` is written to the OS keyring and never to disk; the
    record keeps a ``password_ref`` pointing at it.
    """
    prof = dict(profile)
    pid = str(prof.get("id") or "").strip()
    if not pid:
        raise ValueError("profile needs an id")

    if proxy_password:
        proxy = dict(prof.get("proxy") or {})
        try:
            import keyring
            keyring.set_password(_KEYRING_SERVICE, pid, proxy_password)
            proxy["password_ref"] = f"{_KEYRING_SERVICE}/{pid}"
            proxy.pop("password", None)  # never persist the literal
            prof["proxy"] = proxy
        except Exception as exc:
            raise RuntimeError(
                f"could not store the proxy password in the keyring ({exc}); "
                f"refusing to write it to disk instead"
            ) from exc

    reg = _load_raw()
    profiles = [p for p in (reg.get("profiles") or []) if str(p.get("id")) != pid]
    profiles.append(prof)
    reg["profiles"] = profiles
    _save_raw(reg)
    logger.info(f"[browser-registry] saved profile '{pid}' ({prof.get('label') or ''})")
    return prof


def delete_profile(profile_id: str, forget_password: bool = True) -> bool:
    """Remove a record. Does NOT delete the user-data-dir — that is the session."""
    reg = _load_raw()
    before = len(reg.get("profiles") or [])
    reg["profiles"] = [p for p in (reg.get("profiles") or [])
                       if str(p.get("id")) != str(profile_id)]
    if len(reg["profiles"]) == before:
        return False
    _save_raw(reg)
    if forget_password:
        try:
            import keyring
            keyring.delete_password(_KEYRING_SERVICE, str(profile_id))
        except Exception:
            pass
    logger.info(f"[browser-registry] deleted profile '{profile_id}'")
    return True


def get_proxy_password(profile: dict) -> str:
    """Read the proxy password for *profile* out of the keyring. '' if none."""
    ref = ((profile.get("proxy") or {}).get("password_ref") or "").strip()
    if not ref:
        return ""
    service, _, account = ref.partition("/")
    try:
        import keyring
        return keyring.get_password(service or _KEYRING_SERVICE,
                                    account or str(profile.get("id"))) or ""
    except Exception as exc:
        logger.warning(
            f"[browser-registry] could not read the proxy password for "
            f"'{profile.get('id')}' ({exc}); the browser will start without auth"
        )
        return ""


def make_profile(
    profile_id: str,
    label: str = "",
    domain_name: str = "",
    user_data_dir: str = "",
    browser_path: str = "",
    browser_version: str = "",
    proxy: Optional[dict] = None,
    proxy_bypass: Optional[list] = None,
    fingerprint_profile: str = "",
    locale: str = "en-US",
    imported_from: Optional[dict] = None,
    store_id: str = "",
    machine_id: str = "",
) -> dict:
    """Build a record with the conventions applied (dir naming, salt)."""
    if not user_data_dir:
        user_data_dir = str(browser_data_root() / f"{profile_id}_{install_salt()}")
    prox = dict(proxy or {})
    prox.pop("password", None)  # callers pass it to save_profile instead
    return {
        "id": profile_id,
        "label": label or profile_id,
        "domain_name": domain_name,
        "user_data_dir": user_data_dir,
        "install_salt": install_salt(),
        "browser": {"path": browser_path, "version": browser_version},
        "proxy": prox,
        "proxy_bypass": list(proxy_bypass or []),
        "fingerprint_profile": fingerprint_profile,
        "locale": locale,
        "imported_from": dict(imported_from or {}),
        # Which shop this login belongs to, and which machine holds it. A
        # profile IS a store's login, so without these an operator with eight
        # stores on three machines cannot tell which profile is which.
        "store_id": store_id,
        "machine_id": machine_id,
        # A brand new profile has never been signed in. Saying so explicitly
        # is what lets provisioning finish and hand the operator a precise
        # "log in to these two stores" list instead of a silent failure at the
        # first customer message.
        "login_state": LOGIN_NEEDED,
        "login_checked_at": 0,
        "login_detail": "",
    }



# ── Login state ──────────────────────────────────────────────────────
# A profile is a live seller login, and logins expire. For one store that is
# a nuisance you notice; for eight stores across three machines it is the
# difference between "store 6 has been silently offline since Tuesday" and a
# list of what needs attention. The browser being UP (profile_status) says
# nothing about whether the session inside it still works.

LOGIN_UNKNOWN = "unknown"       # never checked
LOGIN_OK = "ok"                 # a run confirmed the session works
LOGIN_NEEDED = "needs_login"    # freshly provisioned, or the session is gone

_LOGIN_STATES = (LOGIN_UNKNOWN, LOGIN_OK, LOGIN_NEEDED)


def set_login_state(profile_id: str, state: str, detail: str = "") -> bool:
    """Record whether this profile's seller session still works.

    Reported by whatever actually found out — a run that reached the site, or
    provisioning that just created the profile. Returns False for an unknown
    profile or an unknown state rather than inventing a record.
    """
    if state not in _LOGIN_STATES:
        logger.warning(f"[browser-registry] ignoring unknown login state {state!r}")
        return False
    prof = get_profile(profile_id)
    if not prof:
        logger.warning(f"[browser-registry] no profile '{profile_id}' to mark {state}")
        return False
    prof = dict(prof)
    prof["login_state"] = state
    prof["login_checked_at"] = int(time.time())
    prof["login_detail"] = str(detail or "")[:500]
    save_profile(prof)
    logger.info(f"[browser-registry] profile '{profile_id}' login state -> {state}")
    return True


def login_state(profile_id: str) -> dict:
    """``{state, checked_at, detail}``. Unknown profile reads as unknown."""
    prof = get_profile(profile_id) or {}
    state = str(prof.get("login_state") or "") or LOGIN_UNKNOWN
    return {
        "state": state if state in _LOGIN_STATES else LOGIN_UNKNOWN,
        "checked_at": int(prof.get("login_checked_at") or 0),
        "detail": str(prof.get("login_detail") or ""),
    }


def profiles_needing_login() -> list[dict]:
    """Every profile whose session needs a human — the provisioning to-do list."""
    return [
        {"id": p.get("id", ""), "label": p.get("label", "") or p.get("id", ""),
         "store_id": p.get("store_id", ""), "machine_id": p.get("machine_id", "")}
        for p in list_profiles()
        if str(p.get("login_state") or LOGIN_NEEDED) == LOGIN_NEEDED
    ]


# ── Syncable descriptor ──────────────────────────────────────────────
# The split the design turns on: a DESCRIPTOR may leave the machine, the
# profile itself must not. The descriptor is what lets the cloud know a
# profile should exist on machine M and show the operator its state; the
# contents -- cookies, localStorage, the session, the proxy password -- are
# what make losing one mean "someone else can act as that seller".
#
# This is an allowlist, never a blocklist with deletions: a field added to a
# profile record later must be opted IN here, so the default for anything new
# is "stays local".

_DESCRIPTOR_FIELDS = (
    "id", "label", "store_id", "machine_id", "domain_name",
    "fingerprint_profile", "locale",
)


def descriptor(profile: dict) -> dict:
    """The part of a profile that is safe to leave this machine.

    Deliberately excludes ``user_data_dir`` (where the session lives, and the
    machine's directory layout), ``install_salt``, anything under ``proxy``
    beyond "is there one", and ``imported_from``. Building it as an allowlist
    means a future field is private until someone decides otherwise.

    Note this function only SHAPES the data — it does not send it anywhere.
    Nothing cloud-bound may reach into this module; see
    tests/unit/test_browser_profile_stays_local.py.
    """
    prof = dict(profile or {})
    out = {k: prof.get(k, "") for k in _DESCRIPTOR_FIELDS}
    browser = prof.get("browser") or {}
    # Which Chromium wrote the profile matters: a profile written by one build
    # is not always safe to open with another.
    out["browser"] = {
        "version": str(browser.get("version") or ""),
    }
    proxy = prof.get("proxy") or {}
    # Whether an egress proxy is configured, never which one or its credentials.
    out["has_proxy"] = bool(proxy.get("host") or proxy.get("port"))
    state = login_state(prof.get("id", ""))
    out["login_state"] = state["state"]
    out["login_checked_at"] = state["checked_at"]
    return out

