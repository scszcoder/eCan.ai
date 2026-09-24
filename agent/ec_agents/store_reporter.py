"""Tell the cloud which stores this machine is serving.

The observed half of the store registry: ``store_report`` from the machine,
``store_assign`` from the owner, and ``store_list`` shows where they disagree.

A store here is an EXPLICIT ``task_vars.store_id`` on a task of an agent this
machine launches. The URL fallback of ``resolve_store_id`` is deliberately not
used: on 飞鸽 it yields the same value for every seller, and the server refuses
it anyway.

Login state comes from a browser profile tagged with that store, sent as the
allowlisted ``descriptor()`` only -- never the profile. This module lives
outside ``agent/cloud_api`` because a cloud-bound module may not read the
profile registry (tests/unit/test_browser_profile_stays_local.py); the
reduction to a descriptor happens here, and store_api only forwards it.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from utils.logger_helper import logger_helper as logger


def _explicit_store_id(task) -> str:
    from agent.ec_skills.prompt_variable_providers import STORE_ID_VAR

    md = getattr(task, "metadata", None)
    if not isinstance(md, dict):
        return ""
    task_vars = md.get("task_vars")
    if not isinstance(task_vars, dict):
        return ""
    return str(task_vars.get(STORE_ID_VAR) or "").strip()


def local_store_ids(mainwin) -> List[str]:
    """Explicit store ids of every task on an agent this machine launches."""
    from agent.ec_agents.vehicle_affinity import agent_launch_allowed

    seen: List[str] = []
    for agent in list(getattr(mainwin, "agents", None) or []):
        try:
            allowed, _ = agent_launch_allowed(agent)
        except Exception:
            allowed = False
        if not allowed:
            continue
        for task in list(getattr(agent, "tasks", None) or []):
            sid = _explicit_store_id(task)
            if sid and sid not in seen:
                seen.append(sid)
    return seen


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
        items = build_local_store_report(mainwin)
        if not items:
            return None
        vid = resolve_local_vehicle_id(mainwin)
        if not vid:
            logger.warning("[StoreReporter] no stable machine id; skipping store report")
            return None
        return store_report(vid, items)
    except StoreApiUnavailable as exc:
        logger.warning(f"[StoreReporter] store report skipped: {exc}")
    except StoreApiError as exc:
        logger.warning(f"[StoreReporter] store report failed: {exc}")
    except Exception as exc:
        logger.error(f"[StoreReporter] store report crashed: {exc}")
    return None
