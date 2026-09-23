"""Browser profile handlers — logged-in session + proxy + fingerprint.

A *browser profile* is one logged-in identity on one site: the Etsy store, the
eBay seller account. It binds a user-data-dir (the session), a proxy (the
egress that site has seen), a fingerprint preset, and the Chromium binary that
wrote the profile. ``agent.ec_skills.browser_use_extension.fingerprint`` owns
all of that; this module is only the window the GUI looks through.

**The DTO is the contract, and it is deliberately not the storage shape.**
Everything the front end sees goes through ``_to_dto`` / ``_from_dto``. The
registry file's layout, where the password lives, and whether a profile is
local at all are free to change behind them — which matters, because the shape
of this feature is not settled: profiles may yet grow a cloud half, a vendor
may be driven in place rather than imported, and the fingerprint model may be
replaced outright if it turns out not to hold up over time. When that happens
the mapping functions change and the page does not.

Two rules the mapping enforces and the GUI therefore cannot break:

* **A password never crosses this boundary.** It goes in through ``save`` to
  the OS keyring and comes back only as ``has_password``. Nothing this module
  returns can leak one into a log, a devtools panel, or a bug report.
* **Status is live, not stored.** ``running``/``port`` are read from the
  browser itself on every call, so the page cannot show a stale port for a
  browser that died, or miss one a skill run started behind its back.
"""

import re
import traceback
from typing import Any, Dict, Optional

from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import (
    IPCRequest,
    IPCResponse,
    create_error_response,
    create_success_response,
)
from utils.logger_helper import logger_helper as logger

# A profile id becomes a directory name (``<id>_<salt>``) and a keyring account.
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


def _fp():
    """The fingerprint package. Imported lazily — it pulls in keyring."""
    from agent.ec_skills.browser_use_extension.fingerprint import (
        fingerprint_browser,
        fingerprint_service,
        profile_registry,
    )
    return profile_registry, fingerprint_browser, fingerprint_service


# ---------------------------------------------------------------------------
# The DTO boundary
# ---------------------------------------------------------------------------

def _to_dto(profile: Dict[str, Any], status: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Registry record -> what the front end sees. Never includes a password."""
    proxy = profile.get("proxy") or {}
    browser = profile.get("browser") or {}
    return {
        "id": profile.get("id", ""),
        "label": profile.get("label", "") or profile.get("id", ""),
        "domain": profile.get("domain_name", ""),
        "locale": profile.get("locale", "") or "en-US",
        "user_data_dir": profile.get("user_data_dir", ""),
        "browser": {
            "path": browser.get("path", ""),
            "version": browser.get("version", ""),
        },
        "proxy": {
            "scheme": proxy.get("scheme", "") or "socks5",
            "host": proxy.get("host", ""),
            "port": int(proxy.get("port") or 0),
            "username": proxy.get("username", ""),
            # The password itself stays in the keyring. This is the only thing
            # the GUI is told about it.
            "has_password": bool(proxy.get("password_ref")),
            "bypass": list(profile.get("proxy_bypass") or []),
        },
        "fingerprint_profile": profile.get("fingerprint_profile", "") or "",
        "imported_from": dict(profile.get("imported_from") or {}),
        # Which shop this login is for, and whether the session still works.
        # profile_status below answers "is the browser up", which says nothing
        # about whether the seller session inside it is still valid -- the
        # question an operator with several stores actually has.
        "store_id": profile.get("store_id", "") or "",
        "machine_id": profile.get("machine_id", "") or "",
        "login": {
            "state": profile.get("login_state", "") or "unknown",
            "checked_at": int(profile.get("login_checked_at") or 0),
            "detail": profile.get("login_detail", "") or "",
        },
        "status": status if status is not None else {},
    }


def _from_dto(dto: Dict[str, Any], existing: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """What the front end sent -> a registry record.

    ``existing`` is the stored record, if this is an edit. Fields the GUI does
    not own — the user-data-dir, the install salt, where the password lives,
    what it was imported from — are carried over from it rather than accepted
    from the client, so a round trip through the page cannot lose the session
    or orphan the keyring entry.
    """
    proxy_in = dto.get("proxy") or {}
    browser_in = dto.get("browser") or {}

    proxy: Dict[str, Any] = {}
    if (proxy_in.get("host") or "").strip():
        proxy = {
            "scheme": (proxy_in.get("scheme") or "socks5").strip(),
            "host": (proxy_in.get("host") or "").strip(),
            "port": int(proxy_in.get("port") or 0),
            "username": (proxy_in.get("username") or "").strip(),
        }
        # Keep pointing at the stored password unless a new one is being saved
        # (save_profile rewrites the ref when it is).
        ref = ((existing or {}).get("proxy") or {}).get("password_ref")
        if ref:
            proxy["password_ref"] = ref

    record = {
        "id": (dto.get("id") or "").strip(),
        "label": (dto.get("label") or "").strip() or (dto.get("id") or "").strip(),
        "domain_name": (dto.get("domain") or "").strip(),
        "locale": (dto.get("locale") or "en-US").strip(),
        "proxy": proxy,
        "proxy_bypass": [s for s in (proxy_in.get("bypass") or []) if str(s).strip()],
        "fingerprint_profile": (dto.get("fingerprint_profile") or "").strip(),
        "browser": {
            "path": (browser_in.get("path") or "").strip(),
            "version": (browser_in.get("version") or "").strip(),
        },
    }

    if existing:
        # The session directory is the one thing that must never move.
        record["user_data_dir"] = existing.get("user_data_dir", "")
        record["install_salt"] = existing.get("install_salt", "")
        record["imported_from"] = dict(existing.get("imported_from") or {})
        if not record["browser"]["path"]:
            record["browser"] = dict(existing.get("browser") or {})
    else:
        record["imported_from"] = {}

    return record


def _dto_with_status(profile: Dict[str, Any]) -> Dict[str, Any]:
    _, fb, _svc = _fp()
    try:
        status = fb.profile_status(profile.get("id", ""))
    except Exception as exc:
        logger.warning(f"[browser-profile] status for "
                       f"'{profile.get('id')}' failed: {exc}")
        status = {"running": False, "port": 0, "cdp_url": "", "pid": 0,
                  "relay_port": 0, "relay_alive": False, "owned": False}
    return _to_dto(profile, status)


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------

@IPCHandlerRegistry.handler('browser_profile.list')
def handle_list(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Every registered profile, each with its live browser status."""
    try:
        registry, _fb, _svc = _fp()
        profiles = [_dto_with_status(p) for p in registry.list_profiles()]
        return create_success_response(request, {'profiles': profiles,
                                                 'count': len(profiles)})
    except Exception as e:
        logger.error(f"[browser-profile] list failed: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'BROWSER_PROFILE_ERROR',
                                     f"Failed to list browser profiles: {e}")


@IPCHandlerRegistry.handler('browser_profile.options')
def handle_options(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """The choices the editor offers: fingerprint presets, a default binary.

    Kept separate from the profile list because it changes on a different
    clock — presets ship with the app, profiles are the user's data.
    """
    try:
        _registry, fb, svc = _fp()

        fingerprints = []
        for fp_profile in svc.list_profiles():
            fingerprints.append({
                'id': fp_profile.get('id', ''),
                'name': fp_profile.get('name', '') or fp_profile.get('id', ''),
                'description': fp_profile.get('description', ''),
                'platform': fp_profile.get('platform', ''),
                'locale': fp_profile.get('locale', ''),
                'timezone': fp_profile.get('timezone', ''),
                'source': fp_profile.get('_source', 'bundled'),
            })

        # What a profile with no recorded binary would run today. Shown as the
        # placeholder so the field can be left empty and still be honest.
        try:
            default_browser = fb.resolve_browser_path({})
        except Exception:
            default_browser = ''

        return create_success_response(request, {
            'fingerprints': fingerprints,
            'default_browser_path': default_browser,
            # Import is vendor-shaped data, not a hard-coded menu, so a new
            # vendor is a row here rather than a change to the page.
            'vendors': [
                {'id': 'adspower', 'name': 'AdsPower',
                 'id_label': 'Profile serial', 'default_api_port': 50325,
                 'needs_account': False, 'validated': True},
                # Ziniao's credentials are the account itself, not an API key,
                # so the editor asks for company/username/password instead.
                # NOT yet validated against a live install -- see
                # vendor_import.import_ziniao.
                {'id': 'ziniao', 'name': '\u7d2b\u9e1f Ziniao',
                 'id_label': '\u5e97\u94fa ID (browserOauth)',
                 'default_api_port': 0,
                 'needs_account': True, 'validated': False},
            ],
        })
    except Exception as e:
        logger.error(f"[browser-profile] options failed: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'BROWSER_PROFILE_ERROR',
                                     f"Failed to load browser profile options: {e}")


@IPCHandlerRegistry.handler('browser_profile.status')
def handle_status(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Live status for one profile — for polling while a launch settles."""
    try:
        profile_id = ((params or {}).get('id') or '').strip()
        if not profile_id:
            return create_error_response(request, 'INVALID_PARAMS',
                                         'A profile id is required')
        _registry, fb, _svc = _fp()
        return create_success_response(request, fb.profile_status(profile_id))
    except Exception as e:
        logger.error(f"[browser-profile] status failed: {e}")
        return create_error_response(request, 'BROWSER_PROFILE_ERROR',
                                     f"Failed to read profile status: {e}")


@IPCHandlerRegistry.handler('browser_profile.needs_login')
def handle_needs_login(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Every profile whose seller session still needs a human.

    The provisioning to-do list: a machine can create profiles and install
    skills on its own, but it cannot sign in as the seller, so this is the one
    step that has to come back to a person. Answers it for all stores at once,
    which is the point — one store you would notice, eight you would not.
    """
    try:
        registry, _fb, _svc = _fp()
        pending = registry.profiles_needing_login()
        return create_success_response(request, {
            'profiles': pending,
            'count': len(pending),
        })
    except Exception as e:
        logger.error(f"[browser-profile] needs_login failed: {e}")
        return create_error_response(request, 'BROWSER_PROFILE_ERROR',
                                     f"Failed to list profiles needing login: {e}")


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------

@IPCHandlerRegistry.handler('browser_profile.set_login_state')
def handle_set_login_state(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Record whether this profile's seller session works.

    The operator is the authoritative source right now: they are the one who
    just signed in, and no site-independent check can tell a logged-in store
    page from a logged-out one. A per-site detector can refine this later
    without changing the state model.
    """
    try:
        p = params or {}
        profile_id = (p.get('id') or '').strip()
        state = (p.get('state') or '').strip()
        if not profile_id or not state:
            return create_error_response(request, 'INVALID_PARAMS',
                                         'A profile id and a state are required')
        registry, _fb, _svc = _fp()
        ok = registry.set_login_state(profile_id, state, str(p.get('detail') or ''))
        if not ok:
            return create_error_response(
                request, 'INVALID_PARAMS',
                f"Unknown profile '{profile_id}' or unsupported state '{state}'")
        return create_success_response(request, registry.login_state(profile_id))
    except Exception as e:
        logger.error(f"[browser-profile] set_login_state failed: {e}")
        return create_error_response(request, 'BROWSER_PROFILE_ERROR',
                                     f"Failed to set login state: {e}")


@IPCHandlerRegistry.handler('browser_profile.save')
def handle_save(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Create or update a profile. A new password goes to the OS keyring."""
    try:
        dto = (params or {}).get('profile')
        if not isinstance(dto, dict):
            return create_error_response(request, 'INVALID_PARAMS',
                                         'A profile object is required')

        profile_id = (dto.get('id') or '').strip()
        if not _ID_RE.match(profile_id):
            return create_error_response(
                request, 'INVALID_PARAMS',
                "The id becomes a folder name: letters, digits, '-' and '_' "
                "only, starting with a letter or digit.")

        registry, _fb, _svc = _fp()
        existing = registry.get_profile(profile_id)

        if existing is None and (params or {}).get('create') is False:
            return create_error_response(request, 'NOT_FOUND',
                                         f"No browser profile '{profile_id}'")
        if existing is not None and (params or {}).get('create') is True:
            return create_error_response(
                request, 'ALREADY_EXISTS',
                f"A browser profile '{profile_id}' already exists")

        record = _from_dto(dto, existing)
        if not existing:
            # make_profile applies the directory-naming and salt conventions;
            # nothing else is allowed to invent a user-data-dir.
            base = registry.make_profile(
                profile_id,
                label=record['label'],
                domain_name=record['domain_name'],
                browser_path=record['browser'].get('path', ''),
                browser_version=record['browser'].get('version', ''),
                proxy=record['proxy'],
                proxy_bypass=record['proxy_bypass'],
                fingerprint_profile=record['fingerprint_profile'],
                locale=record['locale'],
            )
            record = {**base, **record,
                      'user_data_dir': base['user_data_dir'],
                      'install_salt': base['install_salt']}

        saved = registry.save_profile(
            record, proxy_password=str((params or {}).get('proxy_password') or ''))
        return create_success_response(request, {'profile': _dto_with_status(saved)})
    except Exception as e:
        logger.error(f"[browser-profile] save failed: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'BROWSER_PROFILE_ERROR',
                                     f"Failed to save browser profile: {e}")


@IPCHandlerRegistry.handler('browser_profile.delete')
def handle_delete(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Remove a profile. The session directory is kept unless asked otherwise.

    The record is cheap to recreate; the logged-in session is not, and once the
    directory is gone the login is gone with it.
    """
    try:
        profile_id = ((params or {}).get('id') or '').strip()
        if not profile_id:
            return create_error_response(request, 'INVALID_PARAMS',
                                         'A profile id is required')
        delete_session = bool((params or {}).get('delete_session'))

        registry, fb, _svc = _fp()
        profile = registry.get_profile(profile_id)
        if not profile:
            return create_error_response(request, 'NOT_FOUND',
                                         f"No browser profile '{profile_id}'")

        if fb.profile_status(profile_id).get('running'):
            return create_error_response(
                request, 'PROFILE_RUNNING',
                f"'{profile_id}' is still open. Stop it first — closing the "
                f"browser is what writes its session out.")

        user_data_dir = profile.get('user_data_dir', '')
        registry.delete_profile(profile_id)

        removed_session = False
        if delete_session and user_data_dir:
            import shutil
            try:
                shutil.rmtree(user_data_dir)
                removed_session = True
            except Exception as exc:
                logger.warning(f"[browser-profile] could not delete "
                               f"{user_data_dir}: {exc}")

        return create_success_response(request, {
            'id': profile_id,
            'session_deleted': removed_session,
            'session_kept_at': '' if removed_session else user_data_dir,
        })
    except Exception as e:
        logger.error(f"[browser-profile] delete failed: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'BROWSER_PROFILE_ERROR',
                                     f"Failed to delete browser profile: {e}")


# ---------------------------------------------------------------------------
# Lifecycle — background, because each of these blocks for seconds to minutes
# ---------------------------------------------------------------------------

@IPCHandlerRegistry.background_handler('browser_profile.launch')
def handle_launch(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Open a profile's browser.

    Worth knowing: the SOCKS relay lives in whichever process launches, so a
    browser opened from here keeps a working proxy for as long as the app is
    running — longer than one opened by a single CLI command.
    """
    try:
        profile_id = ((params or {}).get('id') or '').strip()
        if not profile_id:
            return create_error_response(request, 'INVALID_PARAMS',
                                         'A profile id is required')
        start_url = ((params or {}).get('start_url') or '').strip()

        _registry, fb, _svc = _fp()
        launched = fb.launch_profile(
            profile_id, start_url=start_url or 'about:blank')
        return create_success_response(request, {
            'id': profile_id,
            'cdp_url': launched.cdp_url,
            'port': launched.debug_port,
            'attached': launched.attached,
            'status': fb.profile_status(profile_id),
        })
    except Exception as e:
        logger.error(f"[browser-profile] launch failed: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'BROWSER_LAUNCH_FAILED', str(e))


@IPCHandlerRegistry.background_handler('browser_profile.stop')
def handle_stop(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Close a profile's browser, letting it flush cookies on the way out."""
    try:
        profile_id = ((params or {}).get('id') or '').strip()
        if not profile_id:
            return create_error_response(request, 'INVALID_PARAMS',
                                         'A profile id is required')
        _registry, fb, _svc = _fp()
        closed = fb.close_profile(profile_id)
        return create_success_response(request, {
            'id': profile_id,
            'closed': closed,
            'status': fb.profile_status(profile_id),
        })
    except Exception as e:
        logger.error(f"[browser-profile] stop failed: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'BROWSER_PROFILE_ERROR',
                                     f"Failed to stop the browser: {e}")


@IPCHandlerRegistry.background_handler('browser_profile.import_vendor')
def handle_import_vendor(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Copy a logged-in profile out of an anti-detect browser.

    The vendor profile is started briefly and then stopped — its directory is
    only visible on the running process's command line — so this closes it if
    the user has it open. Minutes, not seconds, on a large profile.
    """
    try:
        p = params or {}
        vendor = (p.get('vendor') or 'adspower').strip()
        vendor_profile_id = (p.get('vendor_profile_id') or '').strip()
        new_id = (p.get('id') or '').strip()

        if not vendor_profile_id:
            return create_error_response(request, 'INVALID_PARAMS',
                                         "The vendor's profile id is required")
        if not _ID_RE.match(new_id):
            return create_error_response(
                request, 'INVALID_PARAMS',
                "The id becomes a folder name: letters, digits, '-' and '_' "
                "only, starting with a letter or digit.")
        if vendor not in ('adspower', 'ziniao'):
            return create_error_response(request, 'UNSUPPORTED_VENDOR',
                                         f"Cannot import from '{vendor}' yet")

        from agent.ec_skills.browser_use_extension.fingerprint import vendor_import
        common = dict(
            label=(p.get('label') or '').strip(),
            fingerprint_profile=(p.get('fingerprint_profile') or '').strip(),
            overwrite=bool(p.get('overwrite')),
        )
        if vendor == 'ziniao':
            # Ziniao authenticates with the account, not an API key, and the
            # credentials already live in Settings > Browser Automation >
            # Providers -- fall back to those so the import form only has to
            # ask for the store id.
            zn = {}
            try:
                from gui.ipc.w2p_handlers.browser_use_handler import (
                    load_browser_use_settings,
                )
                zn = ((load_browser_use_settings() or {})
                      .get('browserProviders') or {}).get('ziniao') or {}
            except Exception as exc:
                logger.warning(f"[browser-profile] could not read Ziniao "
                               f"settings ({exc}); using the request only")
            record = vendor_import.import_ziniao(
                vendor_profile_id,
                new_id,
                api_url=(p.get('api_url') or zn.get('api_url') or '').strip(),
                api_port=int(p.get('api_port') or zn.get('api_port') or 0),
                company=(p.get('company') or zn.get('company') or '').strip(),
                username=(p.get('username') or zn.get('username') or '').strip(),
                password=(p.get('password') or zn.get('password') or ''),
                use_socket=bool(p.get('use_socket', zn.get('use_socket'))),
                **common,
            )
        else:
            record = vendor_import.import_adspower(
                vendor_profile_id,
                new_id,
                api_key=(p.get('api_key') or '').strip(),
                api_port=int(p.get('api_port') or 50325),
                api_url=(p.get('api_url') or '').strip(),
                **common,
            )
        return create_success_response(request, {'profile': _dto_with_status(record)})
    except Exception as e:
        logger.error(f"[browser-profile] import failed: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'BROWSER_IMPORT_FAILED', str(e))
