"""Stores and machines: the client half of the cloud store registry.

A store is keyed by ``(account, store_id)``, where ``store_id`` is the same
free-text value Fast Deploy writes into ``task_vars.store_id`` and the proxy
receives as ``X-Ecan-Store-Id``. That is what joins a store to its LLM cost, so
the three have to stay the same string.

Five actions on ``ecbAccountManager``, the same route and bearer ``turn_queue``
already uses — reused from there rather than re-derived, because two ways of
picking the credential is how ``pod_list`` ended up 401-ing against a session
that was making GraphQL calls perfectly well:

    store_report   this machine says what it observes
    store_list     desired vs observed, plus 30-day cost
    store_assign   the owner says where a store should run
    store_claim    a machine takes an UNASSIGNED store (atomic; one winner)
    store_archive  hide or restore

Two things this deliberately does not do.

It never sends an owner — the server takes that from the verified identity, and
a client-supplied owner would be a claim, not a fact.

And **it never reaches for a browser profile.** ``store_report`` carries a
profile *descriptor*: the allowlisted subset — id, label, store, machine,
locale, whether a proxy exists, login state — that its CALLER has already
reduced it to. This module receives a dict and forwards it; it does not know
where profiles live and must not learn, because a cloud-bound module that can
read one is a cloud-bound module that can upload a live seller session. The
server re-applies its own allowlist on top. See
``tests/unit/test_browser_profile_stays_local.py``, which enforces that
separation for this whole directory.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import requests

from utils.logger_helper import logger_helper as logger

DEFAULT_TIMEOUT_S = 20.0

# Max per the server contract; sending more gets the whole call rejected.
MAX_STORES_PER_REPORT = 50

VALID_LOGIN_STATES = ("unknown", "ok", "needs_login")


class StoreApiError(RuntimeError):
    """The call reached the server and was refused."""


class StoreApiUnavailable(StoreApiError):
    """No endpoint, no credential, or the credential was rejected."""


def looks_url_derived(store_id: str) -> bool:
    """Whether ``store_id`` is a URL-shaped value the server will refuse.

    On 飞鸽 every seller works out of the same workstation URL, so a
    URL-derived id is identical for every store — accepting it would merge them
    into one healthy-looking row, with one bucket of cost and one set of
    per-store settings. Checked here as well as on the server so the operator
    is told at the point they can still fix it.
    """
    value = str(store_id or "").strip().lower()
    if not value:
        return False
    if value.startswith("http://") or value.startswith("https://"):
        return True
    # host.tld/path — a bare domain with a path is the same mistake.
    head = value.split("/", 1)
    return len(head) == 2 and "." in head[0] and bool(head[1])


def _call(action: str, payload: Dict[str, Any],
          timeout: float = DEFAULT_TIMEOUT_S) -> Dict[str, Any]:
    """POST one action and return its JSON body."""
    from agent.cloud_api.turn_queue import (
        _account_manager_url, _session_bearer_token, TurnQueueNotConfigured,
    )

    try:
        url = _account_manager_url()
    except TurnQueueNotConfigured as exc:
        raise StoreApiUnavailable(str(exc)) from exc

    token = _session_bearer_token()
    if not token:
        raise StoreApiUnavailable(
            "no session credential for the store API; sign in first"
        )

    try:
        resp = requests.post(
            url,
            json={"action": action, "input": payload},
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {token}"},
            timeout=timeout,
        )
        status, text = resp.status_code, resp.text
    except Exception as exc:
        raise StoreApiError(f"{action} transport error: {exc}") from exc

    try:
        data = json.loads(text or "{}")
    except Exception:
        raise StoreApiError(f"{action} returned non-JSON (HTTP {status}): {text[:200]}")

    if status == 401:
        raise StoreApiUnavailable(
            f"{action} rejected this session (HTTP 401): "
            f"{data.get('message') or 'unauthorized'}. Signing in again fixes a "
            f"credential that is merely expired."
        )
    if status >= 400 or data.get("success") is False:
        raise StoreApiError(
            f"{action} failed (HTTP {status}): "
            f"{data.get('error') or data.get('message') or text[:200]}"
        )
    return data


def build_store_report_item(store_id: str, *, platform: str = "",
                            label: str = "", login_state: str = "unknown",
                            profile: Optional[dict] = None) -> Dict[str, Any]:
    """One entry of a ``store_report``. Raises on a value the server refuses."""
    sid = str(store_id or "").strip()
    if not sid:
        raise ValueError("store_id is required")
    if looks_url_derived(sid):
        raise ValueError(
            f"store_id {sid!r} looks URL-derived. Every 飞鸽 seller shares one "
            f"workstation URL, so this would merge every store into one row — "
            f"give the store its own id in Fast Deploy."
        )
    state = str(login_state or "unknown").strip()
    if state not in VALID_LOGIN_STATES:
        raise ValueError(
            f"login_state {state!r} is not one of {VALID_LOGIN_STATES}"
        )
    item: Dict[str, Any] = {"store_id": sid, "login_state": state}
    if platform:
        item["platform"] = str(platform)
    if label:
        item["label"] = str(label)
    if profile:
        # Forwarded verbatim, and it must already be a descriptor: an allowlist
        # that carries no session, no proxy password and no user-data
        # directory. Building it is the caller's job precisely so this module
        # never has to touch the registry.
        item["profile"] = profile
    return item


def build_store_release_item(store_id: str) -> Dict[str, Any]:
    """A ``store_report`` entry saying this machine STOPPED running the store.

    Clears the observation only if this machine holds it; the machine taking
    over a moved store waits for exactly this before it starts.
    """
    sid = str(store_id or "").strip()
    if not sid:
        raise ValueError("store_id is required")
    return {"store_id": sid, "running": False}


def store_report(vehicle_id: str, stores: List[Dict[str, Any]],
                 timeout: float = DEFAULT_TIMEOUT_S) -> Dict[str, Any]:
    """Tell the cloud what this machine observes.

    ``vehicle_id`` must be the id the vehicles heartbeat registers, because
    ``store_assign`` validates against that row — a second identity here makes
    every assignment 404 against a machine that is plainly online.

    Never changes an assignment; this is observation, not desired state.
    """
    vid = str(vehicle_id or "").strip()
    if not vid:
        raise ValueError("vehicle_id is required")
    if not stores:
        return {"results": [], "accepted": 0, "rejected": 0}
    if len(stores) > MAX_STORES_PER_REPORT:
        raise ValueError(
            f"{len(stores)} stores in one report; the server accepts at most "
            f"{MAX_STORES_PER_REPORT}"
        )

    data = _call("store_report", {"vehicle_id": vid, "stores": stores}, timeout)

    # A rejected item is a configuration problem the operator can fix, so it is
    # worth a WARNING each rather than a silent count.
    for result in (data.get("results") or []):
        if not result.get("ok"):
            logger.warning(
                f"[StoreApi] store {result.get('storeId')!r} rejected: "
                f"{result.get('error') or 'no reason given'}"
            )
    logger.info(
        f"[StoreApi] reported {len(stores)} store(s) from {vid[:8]}..: "
        f"accepted={data.get('accepted')} rejected={data.get('rejected')}"
    )
    return data


def store_list(vehicle_id: str = "", include_archived: bool = False,
               timeout: float = DEFAULT_TIMEOUT_S) -> Dict[str, Any]:
    """Desired vs observed placement, plus 30-day cost.

    With ``vehicle_id`` this is a machine asking "what should I be running?";
    without it, the whole account — the data behind a cross-store screen.
    """
    payload: Dict[str, Any] = {"include_archived": bool(include_archived)}
    if vehicle_id:
        payload["vehicle_id"] = str(vehicle_id).strip()
    return _call("store_list", payload, timeout)


def store_assign(store_id: str, vehicle_id: Optional[str], *,
                 platform: str = "", label: str = "",
                 timeout: float = DEFAULT_TIMEOUT_S) -> Dict[str, Any]:
    """Say where a store should run. ``vehicle_id=None`` unassigns it.

    Also how a store is defined before any machine has reported it, which is
    step one of remote deployment.
    """
    sid = str(store_id or "").strip()
    if not sid:
        raise ValueError("store_id is required")
    if looks_url_derived(sid):
        raise ValueError(f"store_id {sid!r} looks URL-derived; give the store its own id")

    payload: Dict[str, Any] = {"store_id": sid, "vehicle_id": vehicle_id or None}
    if platform:
        payload["platform"] = platform
    if label:
        payload["label"] = label

    data = _call("store_assign", payload, timeout)
    # Advisory, not failure: the machine is offline, or it reports ["qa"]
    # without "front_desk" and so has no desktop session for a chat front desk.
    for warning in (data.get("warnings") or []):
        logger.warning(f"[StoreApi] assign {sid!r}: {warning}")
    return data


def store_claim(store_id: str, vehicle_id: str,
                timeout: float = DEFAULT_TIMEOUT_S) -> Dict[str, Any]:
    """Claim an UNASSIGNED store for this machine before running it.

    Atomic on the server: of two machines racing for one store exactly one gets
    ``won: True``, and the loser must not run it. Never overrides an owner's
    assignment; idempotent for the machine that already holds it.
    """
    sid = str(store_id or "").strip()
    vid = str(vehicle_id or "").strip()
    if not sid or not vid:
        raise ValueError("store_id and vehicle_id are required")
    return _call("store_claim", {"store_id": sid, "vehicle_id": vid}, timeout)


def store_archive(store_id: str, restore: bool = False,
                  timeout: float = DEFAULT_TIMEOUT_S) -> Dict[str, Any]:
    """Hide a store from listings, or bring it back."""
    sid = str(store_id or "").strip()
    if not sid:
        raise ValueError("store_id is required")
    payload: Dict[str, Any] = {"store_id": sid}
    if restore:
        payload["restore"] = True
    return _call("store_archive", payload, timeout)
