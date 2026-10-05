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


# (key, English name, Chinese name) -- mirrors PLATFORMS in
# gui_v2/src/components/FastDeploy/scenarios.tsx; tests/unit/test_store_platform.py
# fails when the two drift.
_PLATFORMS = [
    ("douyin", "Douyin (抖店)", "抖店"), ("tmall", "T-Mall", "天猫"), ("amazon", "Amazon", "亚马逊"),
    ("ebay", "eBay", "eBay"), ("etsy", "Etsy", "Etsy"), ("shopify", "Shopify", "Shopify"),
    ("tiktok", "TikTok Shop", "TikTok 店铺"), ("pinduoduo", "Pinduoduo", "拼多多"), ("temu", "Temu", "Temu"),
    ("shein", "SHEIN", "希音 (SHEIN)"), ("walmart", "Walmart", "沃尔玛"), ("jd", "JD.com", "京东"),
    ("1688", "1688", "1688"), ("alibaba", "Alibaba", "阿里巴巴"), ("kuaishou", "Kuaishou", "快手"),
    ("xiaohongshu", "Xiaohongshu (RED)", "小红书"), ("xianyu", "Xianyu", "闲鱼"), ("meituan", "Meituan", "美团"),
    ("aliexpress", "AliExpress", "速卖通"), ("lazada", "Lazada", "Lazada"), ("shopee", "Shopee", "Shopee"),
    ("mercadolibre", "Mercado Libre", "美客多"), ("coupang", "Coupang", "Coupang"),
    ("facebook_marketplace", "Facebook Marketplace", "Facebook Marketplace"),
    ("craigslist", "Craigslist", "Craigslist"), ("nextdoor", "Nextdoor", "Nextdoor"),
    ("offerup", "OfferUp", "OfferUp"), ("flipkart", "Flipkart", "Flipkart"), ("rakuten", "Rakuten", "乐天"),
    ("otto", "OTTO", "OTTO"),
]
_PLATFORM_BY_NAME = {n.lower(): key for key, en, zh in _PLATFORMS for n in (key, en, zh)}


def normalize_platform(text: Any) -> str:
    """The platform key for a key or a known platform's English/Chinese name
    (case-insensitive); anything else is a custom platform, kept as given.
    A store saved as "天猫" is a tmall store: the Stores form's free-text entry
    stored the name, and Fast Deploy refused it as "not tmall" (2026-10-05)."""
    t = str(text or "").strip()
    return _PLATFORM_BY_NAME.get(t.lower(), t)


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
              "platform": normalize_platform(r.get("platform")),
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
        "platform": normalize_platform(data.get("platform")), "store_urls": urls,
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
            fields[k] = normalize_platform(data[k]) if k == "platform" else data[k]
    if "browser_profile_id" in data:
        pid = str(data.get("browser_profile_id") or "").strip()
        if pid:
            _tag_profile(pid, sid)
        fields["browser_profile_id"] = pid or None
    return {"store": svc.upsert_store(fields),
            # The cloud keeps its own label/platform until the server grows a
            # definition-only action (docs/STORE_SERVER_CONTRACT.md).
            "warnings": []}


def delete_plan(mainwin: Any, store_id: str) -> Dict[str, Any]:
    """What deleting *store_id* removes: the tasks carrying its store id, and the
    agents whose every task is one of them. An agent that also serves another
    store (a shared Q&A pool) is kept; only this store's tasks leave it."""
    from agent.ec_agents.store_overview import _task_store_id
    sid = str(store_id or "").strip()
    tasks: List[dict] = []
    agents: List[dict] = []
    kept_agents: List[dict] = []
    for agent in list(getattr(mainwin, "agents", None) or []):
        card = getattr(agent, "card", None)
        row = {"id": getattr(card, "id", "") or "", "name": getattr(card, "name", "") or ""}
        own = list(getattr(agent, "tasks", None) or [])
        mine = [t for t in own if _task_store_id(t) == sid]
        if not mine:
            continue
        tasks += [{"id": getattr(t, "id", "") or "", "name": getattr(t, "name", "") or "",
                   "agent_id": row["id"]} for t in mine]
        (agents if len(mine) == len(own) else kept_agents).append(row)
    return {"store_id": sid, "agents": agents, "tasks": tasks, "kept_agents": kept_agents}


def delete_store(mainwin: Any, data: Dict[str, Any]) -> Dict[str, Any]:
    """Delete a store with its agents and tasks (see :func:`delete_plan`).

    ``dry_run`` returns the plan only. The store's browser login profile is
    kept (Settings -> Browser Profiles removes it). Agents are stopped before
    they are deleted, so a store's front desk does not keep answering.
    """
    sid = str(data.get("store_id") or "").strip()
    if not sid:
        raise ValueError("store_id is required")
    plan = delete_plan(mainwin, sid)
    if data.get("dry_run"):
        return {"plan": plan}

    username = str(data.get("username") or "").strip()
    if not username:
        raise ValueError("username is required")
    from gui.ipc.w2p_handlers.agent_handler import handle_delete_agent
    from gui.ipc.w2p_handlers.task_handler import handle_delete_agent_task

    def _ok(resp: Any) -> bool:
        return isinstance(resp, dict) and resp.get("status") == "success"

    failed: List[str] = []
    doomed = {a["id"] for a in plan["agents"]}
    for agent in list(getattr(mainwin, "agents", None) or []):
        if getattr(getattr(agent, "card", None), "id", None) in doomed:
            try:
                agent.stop(f"store {sid} deleted")
            except Exception as e:
                logger.warning(f"[store_catalog] stopping agent before delete failed: {e}")
    if doomed:
        resp = handle_delete_agent({"id": f"store_delete_{sid}", "method": "delete_agent"},
                                   {"username": username, "agent_id": sorted(doomed)})
        if not _ok(resp):
            failed.append(f"agents: {(resp or {}).get('error')}")
    for t in plan["tasks"]:
        if not t["id"]:
            continue
        resp = handle_delete_agent_task({"id": f"store_delete_{t['id']}", "method": "delete_agent_task"},
                                        {"username": username, "task_id": t["id"]})
        if not _ok(resp):
            failed.append(f"task {t['name'] or t['id']}: {(resp or {}).get('error')}")

    from agent.cloud_api.store_api import store_delete as cloud_store_delete
    try:
        cloud = cloud_store_delete(sid)
    except Exception as e:
        cloud = {"cloud": "failed", "note": str(e)}
        failed.append(f"cloud: {e}")
    local = _svc(mainwin).delete_store(sid)

    warnings = list(failed)
    if cloud.get("note"):
        warnings.append(cloud["note"])
    if plan["kept_agents"]:
        warnings.append("agents that also serve other stores were kept; this store's tasks "
                        "leave them after the app restarts: "
                        + ", ".join(a["name"] or a["id"] for a in plan["kept_agents"]))
    logger.info(f"[store_catalog] store {sid} deleted: agents={len(doomed)} tasks={len(plan['tasks'])} "
                f"cloud={cloud.get('cloud')} local={local} failed={len(failed)}")
    return {"plan": plan, "cloud": cloud.get("cloud"), "local": local, "warnings": warnings}
