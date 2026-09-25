"""Fleet transfers: fetch another machine's logs, move a store together with its login.

Every machine runs :func:`tick` on each heartbeat and acts on the transfers the
cloud lists for it, in whichever role it has:

* **receiver** -- makes the key pair, opens the LAN listener, publishes both,
  then decrypts and installs what arrives (over the LAN, or from the cloud);
* **source** -- once the receiver is ready, packs the payload, seals it to the
  receiver's key, and sends it over the LAN if the receiver answers there,
  otherwise through the cloud.

While a transfer involving this machine is open, a short loop polls every few
seconds instead of waiting a whole heartbeat. See docs/FLEET_TRANSFER_DESIGN.md.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import shutil
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from utils.logger_helper import logger_helper as logger

FAST_POLL_S = 3.0
MAX_LOG_HOURS = 24 * 7

_lock = threading.RLock()
_keys: Dict[str, bytes] = {}            # transfer_id -> receiver private key (memory only)
_receivers: Dict[str, Any] = {}         # transfer_id -> lan.Receiver
_incoming_stores: Dict[str, str] = {}   # store_id -> transfer_id (a login is on its way here)
_busy: set = set()
_results: Dict[str, Dict[str, Any]] = {}
_fast_loop_running = False
_mainwin = None


class TransferError(RuntimeError):
    pass


def _api():
    from agent.cloud_api import transfer_api
    return transfer_api


def _me(mainwin) -> str:
    from agent.ec_agents.vehicle_affinity import resolve_local_vehicle_id
    me = resolve_local_vehicle_id(mainwin)
    if not me:
        raise TransferError("this machine has no id yet")
    return me


def _work_dir() -> Path:
    from config.app_info import app_info
    d = Path(app_info.appdata_path) / "fleet_transfers"
    d.mkdir(parents=True, exist_ok=True)
    return d


def downloads_dir() -> Path:
    from config.app_info import app_info
    d = Path(app_info.appdata_path) / "fleet_downloads"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _remove(*paths) -> None:
    for p in paths:
        try:
            os.remove(p)
        except OSError:
            pass


# ── asking ───────────────────────────────────────────────────────────

def request_logs(mainwin, source_vehicle_id: str, hours: float = 24) -> Dict[str, Any]:
    """Ask *source_vehicle_id* for its logs; they come to this machine."""
    me = _me(mainwin)
    hours = min(max(float(hours or 24), 1), MAX_LOG_HOURS)
    row = _api().create("logs", source_vehicle_id, me, me, {"hours": hours})
    row = _become_receiver(row)
    _ensure_fast_loop(mainwin)
    return row


def request_store_move(mainwin, store_id: str, to_vehicle_id: str, *, confirmed: bool,
                       profile_id: str = "") -> Dict[str, Any]:
    """Move a store to another machine and bring its login along.

    ``confirmed`` must be True: the operator has been told that a logged-in
    seller session and its proxy credentials are about to be copied to that
    machine (docs/OWN_FINGERPRINT_BROWSER.md -- user-commanded, one login,
    warned first). The transfer is created BEFORE the store is reassigned, so
    the target already knows a login is coming when it sees the assignment.
    """
    if not confirmed:
        raise TransferError("moving a store's login needs the operator's confirmation")
    from agent.cloud_api.store_api import store_assign, store_list
    me = _me(mainwin)
    rows = store_list(include_archived=False).get("stores") or []
    row = next((r for r in rows if r.get("storeId") == store_id), None)
    if row is None:
        raise TransferError(f"store {store_id!r} is not known to the cloud")
    source = row.get("assignedVehicleId") or row.get("reportedVehicleId") or ""
    if not source:
        raise TransferError(f"store {store_id!r} is not on any machine, so there is no login to move")
    if source == to_vehicle_id:
        raise TransferError(f"store {store_id!r} is already on that machine")
    transfer = _api().create("profile", source, to_vehicle_id, me,
                             {"store_id": store_id, "profile_id": profile_id})
    store_assign(store_id, to_vehicle_id)
    _ensure_fast_loop(mainwin)
    return transfer


def list_transfers(mainwin, include_finished: bool = True) -> List[Dict[str, Any]]:
    rows = _api().list_for(_me(mainwin), include_finished=include_finished)
    for r in rows:
        r.update(_results.get(r.get("transfer_id"), {}))
    return rows


def incoming_login_for(store_id: str) -> str:
    """The transfer bringing *store_id*'s login here, or "" -- placement waits for it."""
    with _lock:
        return _incoming_stores.get(store_id, "")


# ── the heartbeat ────────────────────────────────────────────────────

def tick(mainwin) -> None:
    """Act on every open transfer involving this machine. Never raises."""
    global _mainwin
    _mainwin = mainwin
    try:
        me = _me(mainwin)
        rows = _api().list_for(me)
    except Exception as exc:
        logger.debug(f"[fleet] transfer list unavailable: {exc}")
        return
    active = False
    for t in rows:
        try:
            if t.get("status") in ("done", "failed", "expired"):
                continue
            if t.get("receiver_vehicle_id") == me:
                active = True
                _as_receiver(t)
            if t.get("source_vehicle_id") == me:
                active = True
                _as_source(mainwin, t)
        except Exception as exc:
            logger.warning(f"[fleet] transfer {str(t.get('transfer_id'))[:8]}: {exc}")
    _forget_finished({t.get("transfer_id") for t in rows
                      if t.get("status") not in ("done", "failed", "expired")})
    if active:
        _ensure_fast_loop(mainwin)


def _forget_finished(open_ids) -> None:
    """Drop listeners and keys of transfers the cloud no longer lists as open."""
    with _lock:
        for tid in [t for t in list(_keys) if t not in open_ids and t not in _busy]:
            _keys.pop(tid, None)
            rcv = _receivers.pop(tid, None)
            if rcv:
                rcv.stop()
        for sid, tid in list(_incoming_stores.items()):
            if tid not in open_ids:
                _incoming_stores.pop(sid, None)


def _ensure_fast_loop(mainwin) -> None:
    global _fast_loop_running, _mainwin
    _mainwin = mainwin
    with _lock:
        if _fast_loop_running:
            return
        _fast_loop_running = True

    def _loop():
        global _fast_loop_running
        idle = 0
        try:
            while idle < 3:
                time.sleep(FAST_POLL_S)
                tick(_mainwin)
                with _lock:
                    idle = 0 if (_keys or _busy) else idle + 1
        finally:
            with _lock:
                _fast_loop_running = False

    threading.Thread(target=_loop, name="fleet-transfers", daemon=True).start()


# ── receiver ─────────────────────────────────────────────────────────

def _become_receiver(t: Dict[str, Any]) -> Dict[str, Any]:
    from agent.fleet import lan, seal
    tid = t["transfer_id"]
    priv, pub = seal.new_keypair()
    token = secrets.token_urlsafe(24)
    rcv = lan.Receiver(tid, str(_work_dir() / f"{tid}.in"), token)
    port = rcv.start()
    with _lock:
        _keys[tid] = priv
        _receivers[tid] = rcv
        if t.get("kind") == "profile" and t["params"].get("store_id"):
            _incoming_stores[t["params"]["store_id"]] = tid
    return _api().update(tid, status="ready", receiver={
        "pubkey": pub, "lan": {"addrs": lan.private_addrs(), "port": port, "token": token}})


def _as_receiver(t: Dict[str, Any]) -> None:
    tid = t["transfer_id"]
    status = t.get("status")
    with _lock:
        have_key = tid in _keys
        if tid in _busy:
            return
    if status == "requested":
        if not have_key:
            _become_receiver(t)
        return
    if not have_key:
        # Our private key died with a restart; nobody can open this bundle now.
        _api().finish(tid, "failed", "the receiving machine restarted; ask again")
        return
    rcv = _receivers.get(tid)
    if rcv is not None and rcv.received.is_set():
        _spawn(tid, _receive, t, "lan")
    elif status == "uploaded":
        _spawn(tid, _receive, t, "cloud")


def _spawn(tid: str, fn, *args) -> None:
    with _lock:
        if tid in _busy:
            return
        _busy.add(tid)

    def _run():
        try:
            fn(*args)
        except Exception as exc:
            logger.error(f"[fleet] transfer {tid[:8]} failed: {exc}")
            try:
                _api().finish(tid, "failed", str(exc))
            except Exception:
                pass
            _results[tid] = {"error": str(exc)}
        finally:
            with _lock:
                _busy.discard(tid)

    threading.Thread(target=_run, name=f"fleet-{tid[:8]}", daemon=True).start()


def _receive(t: Dict[str, Any], route: str) -> None:
    from agent.fleet import payloads, seal
    tid = t["transfer_id"]
    sealed = str(_work_dir() / f"{tid}.in")
    if route == "cloud":
        _api().get_blob(_api().download_url(tid), sealed)
    plain = str(_work_dir() / f"{tid}.zip")
    with _lock:
        priv = _keys.get(tid)
    try:
        seal.open_file(sealed, plain, priv, tid)
        if t.get("kind") == "logs":
            name = f"{t.get('source_vehicle_id', 'machine')[:12]}-{time.strftime('%Y%m%d-%H%M%S')}.zip"
            dest = downloads_dir() / name
            shutil.move(plain, dest)
            _results[tid] = {"path": str(dest), "route": route}
            logger.info(f"[fleet] logs from {t.get('source_vehicle_id')} saved to {dest} (via {route})")
        else:
            params = t.get("params") or {}
            from agent.ec_agents.vehicle_affinity import resolve_local_vehicle_id
            info = payloads.install_profile(plain, machine_id=resolve_local_vehicle_id(_mainwin) or "",
                                            store_id=params.get("store_id", ""))
            _results[tid] = {"route": route, **info}
            logger.info(f"[fleet] login '{info['profile_id']}' for store {params.get('store_id')!r} "
                        f"installed here (via {route}, {info['cookies']} cookies)")
    finally:
        _remove(sealed, plain)
    _api().finish(tid, "done")
    with _lock:
        _keys.pop(tid, None)
        rcv = _receivers.pop(tid, None)
        for sid, x in list(_incoming_stores.items()):
            if x == tid:
                _incoming_stores.pop(sid, None)
    if rcv:
        rcv.stop()


# ── source ───────────────────────────────────────────────────────────

def _as_source(mainwin, t: Dict[str, Any]) -> None:
    if t.get("status") != "ready":
        return
    if t.get("kind") == "profile":
        sid = (t.get("params") or {}).get("store_id", "")
        from agent.ec_agents.store_reporter import local_store_ids
        if sid in local_store_ids(mainwin):
            logger.info(f"[fleet] store {sid!r} is still running here; its login moves once it stops")
            return
    _spawn(t["transfer_id"], _send, t)


def _profile_for_store(store_id: str, hint: str = "") -> str:
    if hint:
        return hint
    try:
        from agent.ec_agents.store_catalog import _svc
        svc = _svc(_mainwin)
        rec = svc.get_store(store_id) if svc is not None else None
        if rec and rec.get("browser_profile_id"):
            return rec["browser_profile_id"]
    except Exception:
        pass
    from agent.ec_skills.browser_use_extension.fingerprint import profile_registry as reg
    for p in reg.list_profiles():
        if str(p.get("store_id") or "") == store_id and not p.get("moved_to"):
            return str(p.get("id"))
    raise TransferError(f"store {store_id!r} has no login on this machine")


def _send(t: Dict[str, Any]) -> None:
    from agent.fleet import lan, payloads, seal
    tid = t["transfer_id"]
    plain = str(_work_dir() / f"{tid}.out.zip")
    sealed = str(_work_dir() / f"{tid}.out")
    receiver = t.get("receiver") or {}
    try:
        if t.get("kind") == "logs":
            info = payloads.build_logs(plain, (t.get("params") or {}).get("hours", 24))
            profile_id = ""
        else:
            params = t.get("params") or {}
            profile_id = _profile_for_store(params.get("store_id", ""), params.get("profile_id", ""))
            info = payloads.build_profile(profile_id, plain)
        seal.seal_file(plain, sealed, receiver.get("pubkey", ""), tid)
        size = os.path.getsize(sealed)
        digest = _sha256(sealed)
        _api().update(tid, status="sending", size=size, sha256=digest)
        lan_info = receiver.get("lan") or {}
        via = lan.send(lan_info.get("addrs") or [], lan_info.get("port") or 0,
                       lan_info.get("token") or "", tid, sealed)
        if via:
            try:
                _api().update(tid, route="lan")
            except Exception:
                pass    # the receiver may already have finished it -- that is success
            logger.info(f"[fleet] sent {t.get('kind')} ({size} bytes) over the LAN to {via}: {info}")
        else:
            _api().put_blob(_api().upload_url(tid), sealed)
            _api().update(tid, status="uploaded", route="cloud")
            logger.info(f"[fleet] receiver not on this LAN; sent {t.get('kind')} ({size} bytes) "
                        f"through the cloud: {info}")
        if profile_id:
            payloads.mark_moved(profile_id, t.get("receiver_vehicle_id", ""))
    finally:
        _remove(plain, sealed)


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()
