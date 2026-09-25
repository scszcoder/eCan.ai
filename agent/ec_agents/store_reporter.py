"""Tell the cloud which stores this machine is serving.

The observed half of the store registry: ``store_report`` from the machine,
``store_assign`` from the owner, and ``store_list`` shows where they disagree.

A store here is an EXPLICIT ``task_vars.store_id`` on a task of an agent that
is RUNNING on this machine -- not one merely allowed to: store placement may
have gated it out. The URL fallback of ``resolve_store_id`` is deliberately not
used: on 飞鸽 it yields the same value for every seller, and the server refuses
it anyway.

A store the cloud records as running here that no longer is (moved away, or
this process restarted without it) is reported as released, which is what the
machine taking it over waits for.

Login state comes from a browser profile tagged with that store, sent as the
allowlisted ``descriptor()`` only -- never the profile. This module lives
outside ``agent/cloud_api`` because a cloud-bound module may not read the
profile registry (tests/unit/test_browser_profile_stays_local.py); the
reduction to a descriptor happens here, and store_api only forwards it.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from utils.logger_helper import logger_helper as logger


def _store_process_keys() -> List[str]:
    """Stores running in their own store process on this machine (keys = store ids)."""
    try:
        from agent.ec_tasks import worker_supervisor as ws
        return [s["key"] for s in ws.supervisor().status() if s.get("running") and s.get("key")]
    except Exception:
        return []


def local_store_ids(mainwin) -> List[str]:
    """Explicit store ids served on this machine: by an agent RUNNING in this
    process, or by a running store process (store_isolation.py). Without the
    second half, a store moved into its own process would be released to the
    cloud on every heartbeat."""
    from agent.ec_agents.store_placement import store_ids_of_agent

    seen: List[str] = []
    for agent in list(getattr(mainwin, "agents", None) or []):
        if not getattr(agent, "_running", False):
            continue
        for sid in store_ids_of_agent(agent):
            if sid not in seen:
                seen.append(sid)
    for sid in _store_process_keys():
        if sid not in seen:
            seen.append(sid)
    return seen


def stores_to_release(mainwin, me: str, running: List[str]) -> List[str]:
    """Stores the cloud records as running on ``me`` that are not running here."""
    try:
        from agent.ec_agents.store_placement import refresh
        snapshot = refresh(mainwin) or {}
    except Exception:
        return []
    return [sid for sid, e in (snapshot.get("stores") or {}).items()
            if e.get("reported") == me and sid not in running]


def _profiles_by_store() -> Dict[str, dict]:
    """The first profile tagged with each store id, reduced to its descriptor."""
    try:
        from agent.ec_skills.browser_use_extension.fingerprint import profile_registry as reg
        out: Dict[str, dict] = {}
        for prof in reg.list_profiles():
            sid = str(prof.get("store_id") or "").strip()
            if sid and sid not in out:
                out[sid] = reg.descriptor(prof)
        return out
    except Exception as exc:
        logger.warning(f"[StoreReporter] profile registry unreadable, reporting without login state: {exc}")
        return {}


def build_local_store_report(mainwin) -> List[Dict[str, Any]]:
    """The ``stores`` list for one ``store_report``. Invalid ids are skipped, with a reason."""
    from agent.cloud_api.store_api import MAX_STORES_PER_REPORT, build_store_report_item

    profiles = _profiles_by_store()
    items: List[Dict[str, Any]] = []
    for sid in local_store_ids(mainwin):
        profile = profiles.get(sid)
        try:
            items.append(build_store_report_item(
                sid,
                login_state=(profile or {}).get("login_state") or "unknown",
                profile=profile,
            ))
        except ValueError as exc:
            # An operator-fixable config problem, not a code bug.
            logger.warning(f"[StoreReporter] not reporting store {sid!r}: {exc}")
    if len(items) > MAX_STORES_PER_REPORT:
        logger.warning(
            f"[StoreReporter] {len(items)} stores on this machine; reporting the first "
            f"{MAX_STORES_PER_REPORT}, the server's per-report limit"
        )
        items = items[:MAX_STORES_PER_REPORT]
    return items


def report_local_stores(mainwin) -> Optional[dict]:
    """One ``store_report`` for this machine, or None when there is nothing to send.

    Runs after the vehicles heartbeat, under the same id, so the row the server
    validates against already exists. Never raises: a signed-out session or a
    cloud hiccup is expected here and must not disturb the heartbeat.
    """
    from agent.cloud_api.store_api import StoreApiError, StoreApiUnavailable, store_report
    from agent.ec_agents.vehicle_affinity import resolve_local_vehicle_id

    try:
        from agent.cloud_api.store_api import build_store_release_item
        items = build_local_store_report(mainwin)
        vid = resolve_local_vehicle_id(mainwin)
        if not vid:
            if items:
                logger.warning("[StoreReporter] no stable machine id; skipping store report")
            return None
        running = [i["store_id"] for i in items]
        releases = stores_to_release(mainwin, vid, running)
        for sid in releases:
            logger.info(f"[StoreReporter] releasing store {sid!r}: no longer running here")
        items += [build_store_release_item(sid) for sid in releases]
        if not items:
            return None
        return store_report(vid, items)
    except StoreApiUnavailable as exc:
        logger.warning(f"[StoreReporter] store report skipped: {exc}")
    except StoreApiError as exc:
        logger.warning(f"[StoreReporter] store report failed: {exc}")
    except Exception as exc:
        logger.error(f"[StoreReporter] store report crashed: {exc}")
    return None
