"""The local store catalog: define a store first, then deploy into it.

The ``store`` table (agent/db/models/store_model.py) holds a store's
DEFINITION -- name, platform, URLs, login profile. Where it runs stays in the
cloud registry. This module is the one place that writes the catalog, so the
rules live together:

* **Seeding.** Stores that predate the table -- a ``task_vars.store_id`` on a
  task, a row in the cloud registry -- get a record on first sight, never
  overwriting one that exists.
* **Creating.** A new store is validated like the server validates it (no
  URL-derived id: every 飞鸽 seller shares one workstation URL), its browser
  profile is tagged with the store id, and it is defined in the cloud --
  assigned to this machine, or left unassigned for placement to claim.
* **Profiles stay local.** Only the profile's id is recorded, and only here;
  nothing cloud-bound reads it (tests/unit/test_browser_profile_stays_local.py).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from utils.logger_helper import logger_helper as logger

MAX_STORE_ID_LEN = 128   # the server's limit (ecbAccountManager storeIdProblem)


def _svc(mainwin: Any):
    svc = getattr(getattr(mainwin, "ec_db_mgr", None), "store_service", None)
    if svc is None:
        raise RuntimeError("store catalog unavailable (database not initialised)")
    return svc


def store_id_problem(store_id: str) -> Optional[str]:
    """Why ``store_id`` cannot be used, or None. Mirrors the server's check."""
    from agent.cloud_api.store_api import looks_url_derived
    sid = str(store_id or "").strip()
    if not sid:
        return "a store id is required"
    if len(sid) > MAX_STORE_ID_LEN:
        return f"store id is longer than {MAX_STORE_ID_LEN} characters"
    if looks_url_derived(sid):
        return ("store id looks like a URL; every 飞鸽 seller shares one workstation URL, "
                "so give the store its own name")
    return None


def seed(mainwin: Any, cloud_rows: Optional[List[dict]] = None) -> int:
    """Record every store this machine can see that has no record yet."""
    from agent.ec_agents.store_overview import summarize_agents
    svc = _svc(mainwin)
    created = svc.ensure_stores(
        [{"store_id": sid} for sid in summarize_agents(getattr(mainwin, "agents", None) or [])],
        source="seed_tasks")
    if cloud_rows:
        created += svc.ensure_stores(
            [{"store_id": r.get("storeId"), "name": r.get("label") or r.get("storeId"),
              "platform": r.get("platform") or "",
              "status": "archived" if r.get("status") == "archived" else "active"}
             for r in cloud_rows if r.get("storeId")],
            source="seed_cloud")
    return created


def _tag_profile(profile_id: str, store_id: str) -> None:
    from agent.ec_skills.browser_use_extension.fingerprint import profile_registry as reg
    prof = reg.get_profile(profile_id)
    if not prof:
        raise ValueError(f"no browser profile {profile_id!r}")
    if prof.get("store_id") != store_id:
        prof = dict(prof)
        prof["store_id"] = store_id
        reg.save_profile(prof)


def create_store(mainwin: Any, data: Dict[str, Any]) -> Dict[str, Any]:
    """Define a store. Returns ``{"store": row, "warnings": [...]}``; raises ValueError on bad input."""
    sid = str(data.get("store_id") or "").strip()
    problem = store_id_problem(sid)
    if problem:
        raise ValueError(problem)
    svc = _svc(mainwin)
    if svc.get_store(sid):
        raise ValueError(f"a store with id {sid!r} already exists")
    urls = [str(u).strip() for u in (data.get("store_urls") or []) if str(u or "").strip()]
    profile_id = str(data.get("browser_profile_id") or "").strip()
    if profile_id:
        _tag_profile(profile_id, sid)
    row = svc.upsert_store({
        "store_id": sid, "name": str(data.get("name") or sid).strip(),
        "platform": str(data.get("platform") or "").strip(), "store_urls": urls,
        "browser_profile_id": profile_id or None, "source": "ui",
    })

    warnings: List[str] = []
    try:
        from agent.cloud_api.store_api import store_assign
        vehicle_id = None
        if data.get("assign") == "here":
            from agent.ec_agents.vehicle_affinity import resolve_local_vehicle_id
            vehicle_id = resolve_local_vehicle_id(mainwin) or None
        # Defines the store in the cloud registry (a brand-new id, so this
        # cannot clobber an existing assignment).
        res = store_assign(sid, vehicle_id, platform=row["platform"], label=row["name"])
        warnings += list(res.get("warnings") or [])
        svc.mark_cloud_synced(sid)
    except Exception as e:
        logger.warning(f"[StoreCatalog] {sid!r} saved locally; cloud not updated: {e}")
        warnings.append(f"saved on this machine only; the cloud was not updated ({e})")
    return {"store": svc.get_store(sid), "warnings": warnings}


def update_store(mainwin: Any, data: Dict[str, Any]) -> Dict[str, Any]:
    """Edit a store's definition (name, platform, URLs, login profile). Local only for now."""
    sid = str(data.get("store_id") or "").strip()
    svc = _svc(mainwin)
    if not svc.get_store(sid):
        raise ValueError(f"no store {sid!r}")
    fields: Dict[str, Any] = {"store_id": sid}
    for k in ("name", "platform", "store_urls"):
        if k in data:
            fields[k] = data[k]
    if "browser_profile_id" in data:
        pid = str(data.get("browser_profile_id") or "").strip()
        if pid:
            _tag_profile(pid, sid)
        fields["browser_profile_id"] = pid or None
    return {"store": svc.upsert_store(fields),
            # The cloud keeps its own label/platform until the server grows a
            # definition-only action (docs/STORE_SERVER_CONTRACT.md).
            "warnings": []}
