"""Account-level CONFIG vault for store browser profiles (CONFIG-first).

Why: a store's browser profile is its seller login identity. Today it lives on
exactly one machine, so a store cannot be redeployed to another machine (a
pristine "platoon") without rebuilding it by hand. This module lets the small,
non-sensitive CONFIG of a profile -- its fingerprint template, store binding,
locale and login state -- live in the account's cloud so any machine can
materialize the profile and (after a one-time sign-in) run the store.

What leaves the machine: ONLY ``profile_registry.descriptor(profile)`` -- the
allowlisted, security-vetted subset (id, label, store_id, machine_id,
domain_name, fingerprint_profile, locale, browser.version, has_proxy,
login_state). NEVER the ``user_data_dir`` (the live session), ``install_salt``,
proxy host/port/credentials, or cookies. The sensitive profile stays local,
exactly as ``tests/unit/test_browser_profile_stays_local.py`` requires; session
STATE sync is a separate, deferred phase.

Transport mirrors ``gui/ipc/w2p_handlers/skill_file_sync.py``: an AppSync
GraphQL op mints a presigned URL (the desktop holds no bucket secrets), then the
tiny descriptor JSON is PUT/GET directly to object storage.

Gated OFF by default (``ECAN_PROFILE_VAULT``): the backend GraphQL ops
(``requestStoreProfileUploadUrl`` / ``requestStoreProfileDownloadUrl``) are
server work (see docs/PROFILE_VAULT_SERVER_CONTRACT.md). Until they are
deployed, every call here is an instant no-op -- no network, no log spam, no
behavior change. Flip ECAN_PROFILE_VAULT=1 once the server half is live.
"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Dict, Optional

import requests as http_requests

from utils.logger_helper import logger_helper as logger

_MISSING_TTL_SECONDS = 600.0
_missing_download: Dict[str, float] = {}


def _enabled() -> bool:
    return (os.getenv("ECAN_PROFILE_VAULT", "") or "").strip().lower() in ("1", "true", "yes", "on")


def _get_cloud_context() -> Optional[Dict[str, Any]]:
    """{session, token, endpoint, owner} from the running MainWindow, or None."""
    try:
        from app_context import AppContext
        mainwin = AppContext.get_main_window()
        if mainwin is None:
            return None
        token = mainwin.get_auth_token()
        if not token:
            return None
        from agent.cloud_api.cloud_api import normalize_cloud_owner
        owner = normalize_cloud_owner(getattr(mainwin, "user", None) or "")
        if not owner:
            return None
        endpoint = mainwin.getWanApiEndpoint() if hasattr(mainwin, "getWanApiEndpoint") else None
        return {"session": mainwin.session, "token": token, "endpoint": endpoint, "owner": owner}
    except Exception as exc:
        logger.debug(f"[profile_vault] no cloud context: {exc}")
        return None


def _appsync_request(query_string: str, ctx: Dict[str, Any], variables: Optional[Dict] = None) -> Dict:
    from agent.cloud_api.cloud_api import get_appsync_endpoint, _http_auth_header
    endpoint = ctx.get("endpoint") or get_appsync_endpoint()
    headers = {
        "Content-Type": "application/json",
        "Authorization": _http_auth_header(ctx["token"]),
        "cache-control": "no-cache",
    }
    payload: Dict[str, Any] = {"query": query_string}
    if variables:
        payload["variables"] = variables
    try:
        resp = ctx["session"].request(url=endpoint, method="POST", timeout=30,
                                      headers=headers, json=payload)
        return resp.json()
    except Exception as exc:
        logger.debug(f"[profile_vault] AppSync request failed: {exc}")
        return {"errors": [{"errorType": "RequestError", "message": str(exc)}]}


def _request_upload_url(store_id: str, ctx: Dict[str, Any]) -> Optional[Dict[str, str]]:
    mutation = """
        mutation RequestStoreProfileUploadUrl($input: StoreProfileVaultInput!) {
            requestStoreProfileUploadUrl(input: $input) { uploadUrl s3Key expiresIn }
        }
    """
    variables = {"input": {"storeId": store_id, "owner": ctx["owner"]}}
    resp = _appsync_request(mutation, ctx, variables=variables)
    if resp.get("errors"):
        logger.debug(f"[profile_vault] requestStoreProfileUploadUrl error: {resp['errors']}")
        return None
    data = (resp.get("data") or {}).get("requestStoreProfileUploadUrl")
    return data if data and data.get("uploadUrl") else None


def _request_download_url(store_id: str, ctx: Dict[str, Any]) -> Optional[Dict[str, str]]:
    cache_key = f"{ctx['owner']}:{store_id}"
    seen = _missing_download.get(cache_key)
    if seen and (time.time() - seen) < _MISSING_TTL_SECONDS:
        return None
    query = """
        query RequestStoreProfileDownloadUrl($storeId: ID!, $owner: String!) {
            requestStoreProfileDownloadUrl(storeId: $storeId, owner: $owner) {
                downloadUrl s3Key expiresIn
            }
        }
    """
    resp = _appsync_request(query, ctx, variables={"storeId": store_id, "owner": ctx["owner"]})
    if resp.get("errors"):
        _missing_download[cache_key] = time.time()
        logger.debug(f"[profile_vault] no vault descriptor for {store_id!r} yet: {resp['errors']}")
        return None
    data = (resp.get("data") or {}).get("requestStoreProfileDownloadUrl")
    if not data or not data.get("downloadUrl"):
        _missing_download[cache_key] = time.time()
        return None
    _missing_download.pop(cache_key, None)
    return data


def _descriptor_of(profile: dict) -> Dict[str, Any]:
    """The safe, syncable subset — the ONLY thing this module ever uploads."""
    from agent.ec_skills.browser_use_extension.fingerprint import profile_registry
    return profile_registry.descriptor(profile)


def push_descriptor(profile: dict) -> None:
    """Best-effort, async: upload a profile's CONFIG descriptor to the vault.

    Fire-and-forget on a daemon thread (like prompt/skill cloud sync); swallows
    every error. No-op when the vault is disabled or the profile has no store
    binding. Only ``descriptor(profile)`` is sent — never the session or proxy.
    """
    if not _enabled():
        return
    try:
        desc = _descriptor_of(profile)
    except Exception as exc:
        logger.debug(f"[profile_vault] could not shape descriptor: {exc}")
        return
    store_id = str(desc.get("store_id") or "").strip()
    if not store_id:
        return

    def _work():
        try:
            ctx = _get_cloud_context()
            if not ctx:
                return
            slot = _request_upload_url(store_id, ctx)
            if not slot:
                return
            body = json.dumps(desc, ensure_ascii=False).encode("utf-8")
            resp = http_requests.put(slot["uploadUrl"], data=body,
                                     headers={"Content-Type": "application/json"}, timeout=60)
            if resp.status_code in (200, 204):
                logger.info(f"[profile_vault] pushed descriptor for store {store_id!r}")
            else:
                logger.debug(f"[profile_vault] upload failed {resp.status_code} for {store_id!r}")
        except Exception as exc:
            logger.debug(f"[profile_vault] push failed for {store_id!r}: {exc}")

    threading.Thread(target=_work, daemon=True, name="profile-vault-push").start()


def pull_descriptor(store_id: str) -> Optional[Dict[str, Any]]:
    """Synchronous, best-effort: the store's CONFIG descriptor from the vault.

    Returns the descriptor dict, or None when the vault is disabled, there is no
    cloud context, nothing is stored yet, or anything fails — callers then fall
    back to seeding a fresh standard profile.
    """
    store_id = str(store_id or "").strip()
    if not _enabled() or not store_id:
        return None
    try:
        ctx = _get_cloud_context()
        if not ctx:
            return None
        slot = _request_download_url(store_id, ctx)
        if not slot:
            return None
        resp = http_requests.get(slot["downloadUrl"], timeout=60)
        if resp.status_code != 200:
            logger.debug(f"[profile_vault] download {resp.status_code} for {store_id!r}")
            return None
        desc = json.loads(resp.content.decode("utf-8"))
        return desc if isinstance(desc, dict) else None
    except Exception as exc:
        logger.debug(f"[profile_vault] pull failed for {store_id!r}: {exc}")
        return None
