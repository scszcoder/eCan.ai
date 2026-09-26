"""Bring this machine's local database up to date with the account's cloud copy.

Every machine keeps its own SQLite database; the cloud is what they share. A
second machine (a Platoon set up after the Commander, a reinstall, a new PC)
starts with an empty database, and startup builds tasks and agents FROM that
database -- an agent finds its tasks through ``agent_task_rels``, a task its
skill through ``agent_task_skill_rels``. Nothing wrote those rows from the
cloud, so a fresh machine came up with no tasks and agents with nothing to do.

This fills the local database from the cloud BEFORE startup builds anything, so
every machine starts from the same data the machine that created it did:

* agents / tasks the cloud has and this machine doesn't -> inserted;
* a task this machine has that the cloud holds a NEWER copy of -> updated
  (an older or undated cloud copy never overwrites a local edit);
* agent->task and task->skill links -> added when missing (idempotent);
* agents that already exist locally are left to the startup merge.

Rows are owned by this machine's signed-in user, because that is who the local
loaders read (the cloud owner id can be spelled differently, e.g. a WeChat
openid with or without a prefix).

The cloud being slow or unreachable is expected, not an error: the pass logs a
WARNING and startup continues from whatever the local database has.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from utils.logger_helper import logger_helper as logger


# ── cloud reads ──────────────────────────────────────────────────────────

def _cloud_ctx(mainwin):
    token = mainwin.get_auth_token() if hasattr(mainwin, "get_auth_token") else None
    endpoint = mainwin.getWanApiEndpoint() if hasattr(mainwin, "getWanApiEndpoint") else None
    if not token or not endpoint:
        return None
    import requests
    return requests.Session(), token, endpoint


def _as_rows(resp, key_hints=("items", "relationships", "data")) -> Optional[List[dict]]:
    """A cloud list response as a list of dicts; None when the call failed."""
    if isinstance(resp, str):
        try:
            resp = json.loads(resp)
        except Exception:
            return None
    if isinstance(resp, list):
        return [r for r in resp if isinstance(r, dict)]
    if isinstance(resp, dict):
        for k in key_hints:
            if isinstance(resp.get(k), list):
                return [r for r in resp[k] if isinstance(r, dict)]
        if "message" in resp or "errors" in resp:
            return None              # an error object, not "no rows"
        return []
    return None


def _from_cloud(data_type, rows: List[dict]) -> List[dict]:
    from agent.cloud_api.schema_registry import get_schema_registry
    schema = get_schema_registry().get_schema(data_type)
    out = []
    for r in rows:
        try:
            out.append(schema.from_cloud(r))
        except Exception as e:
            logger.debug(f"[cloud_hydrate] unreadable cloud row {r.get('id')}: {e}")
    return out


def fetch_cloud_tasks(ctx) -> Optional[List[dict]]:
    from agent.cloud_api.cloud_api import send_get_agent_tasks_request_to_cloud
    from agent.cloud_api.constants import DataType
    rows = _as_rows(send_get_agent_tasks_request_to_cloud(*ctx))
    return None if rows is None else _from_cloud(DataType.TASK, rows)


def fetch_cloud_agents(ctx) -> Optional[List[dict]]:
    from agent.cloud_api.cloud_api import send_get_agents_request_to_cloud
    from agent.cloud_api.constants import DataType
    rows = _as_rows(send_get_agents_request_to_cloud(*ctx))
    return None if rows is None else _from_cloud(DataType.AGENT, rows)


def fetch_cloud_task_skill_links(ctx) -> Optional[List[dict]]:
    from agent.cloud_api.cloud_api import send_query_task_skill_relations_to_cloud
    session, token, endpoint = ctx
    return _as_rows(send_query_task_skill_relations_to_cloud(
        session, token, {"byowneruser": True}, endpoint))


def fetch_cloud_agent_task_links(ctx) -> Optional[List[dict]]:
    from agent.cloud_api.cloud_api import send_query_agent_task_rels_to_cloud
    session, token, endpoint = ctx
    return _as_rows(send_query_agent_task_rels_to_cloud(
        session, token, {"byowneruser": True}, endpoint))


# ── local writes ─────────────────────────────────────────────────────────

def _columns(model) -> set:
    return {c.key for c in model.__mapper__.column_attrs}


def _json_value(v):
    if isinstance(v, str) and v.strip()[:1] in ("{", "["):
        try:
            return json.loads(v)
        except Exception:
            return v
    return v


def _when(v) -> Optional[datetime]:
    """A cloud/local timestamp (ISO string, epoch s/ms, datetime) as aware UTC."""
    if v in (None, ""):
        return None
    try:
        if isinstance(v, datetime):
            dt = v
        elif isinstance(v, (int, float)) or (isinstance(v, str) and v.strip().isdigit()):
            n = float(v)
            dt = datetime.fromtimestamp(n / 1000.0 if n > 1e11 else n, tz=timezone.utc)
        else:
            dt = datetime.fromisoformat(str(v).strip().replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _row_fields(model, data: dict, owner: str, renames: Dict[str, str] = None) -> dict:
    cols = _columns(model)
    fields = {}
    for k, v in (data or {}).items():
        k = (renames or {}).get(k, k)
        if k in cols and k not in ("created_at", "updated_at", "owner"):
            fields[k] = _json_value(v)
    fields["owner"] = owner
    return fields


def _persist_agents(session, agents: List[dict], owner: str) -> int:
    from agent.db.models.agent_model import DBAgent
    have = {r[0] for r in session.query(DBAgent.id).all()}
    added = 0
    for a in agents:
        aid = str(a.get("id") or "")
        if not aid or aid in have or not a.get("name"):
            continue
        fields = _row_fields(DBAgent, a, owner)
        fields.pop("supervisor_id", None)       # may name an agent not here yet
        fields.pop("avatar_resource_id", None)
        session.add(DBAgent(**fields))
        have.add(aid)
        added += 1
    return added


def _persist_tasks(session, tasks: List[dict], owner: str) -> Dict[str, int]:
    from agent.db.models.task_model import DBAgentTask
    local = {t.id: t for t in session.query(DBAgentTask).all()}
    added = updated = 0
    updated_ids: List[str] = []
    for t in tasks:
        tid = str(t.get("id") or "")
        if not tid or not t.get("name"):
            continue
        fields = _row_fields(DBAgentTask, t, owner, renames={"metadata": "settings"})
        fields.pop("org_id", None)              # an org this machine may not have
        row = local.get(tid)
        if row is None:
            session.add(DBAgentTask(**fields))
            added += 1
            continue
        cloud_at, local_at = _when(t.get("updated_at")), _when(row.updated_at)
        if cloud_at and local_at and (cloud_at - local_at).total_seconds() > 1.0:
            for k, v in fields.items():
                if k not in ("id", "owner"):
                    setattr(row, k, v)
            updated += 1
            updated_ids.append(tid)
    return {"added": added, "updated": updated, "updated_ids": updated_ids}


def _persist_links(session, model, rows: List[dict], a: str, b: str, extra: dict = None) -> list:
    """Adds the missing (a, b) links; returns the pairs it added."""
    have = {(getattr(r, a), getattr(r, b)) for r in session.query(model).all()}
    added = []
    for r in rows or []:
        pair = (str(r.get(a) or ""), str(r.get(b) or ""))
        if not all(pair) or pair in have:
            continue
        session.add(model(**{a: pair[0], b: pair[1], **(extra or {})}))
        have.add(pair)
        added.append(pair)
    return added


# ── prompts and skill files (they live as files, not rows) ────────────────

def hydrate_prompts() -> Dict[str, Any]:
    """Write every cloud prompt this machine has no file for (a node reads its
    prompt from the local file; without it the node runs on its inline stub)."""
    try:
        from gui.ipc.w2p_handlers.prompt_cloud_sync import fetch_cloud_prompts
        from gui.ipc.w2p_handlers import prompt_handler
    except Exception as e:
        return {"skipped": f"prompt sync unavailable: {e}"}
    try:
        have = {p.get("id") for p in prompt_handler._load_all_prompts() if p.get("id")}
        added = []
        for cp in fetch_cloud_prompts() or []:
            pid = cp.get("id")
            if pid and pid not in have:
                prompt_handler._write_prompt_to_file(cp)
                have.add(pid)
                added.append(pid)
        return {"added": added}
    except Exception as e:
        logger.warning(f"[cloud_hydrate] cloud prompts unavailable ({e}) -- using the local copies")
        return {"error": str(e)}


def hydrate_skill_files(ctx, wait_s: float = 45.0) -> Dict[str, Any]:
    """Download the files of this user's own cloud skills that have no folder here
    (subscribed skills are refreshed by refresh_subscribed_skills_from_cloud).
    A skill compiles from its folder -- workflow, data_mapping, bundle, code."""
    import threading
    import time as _time
    try:
        from agent.cloud_api.cloud_api import send_get_agent_skills_request_to_cloud
        from gui.ipc.w2p_handlers.skill_file_sync import _resolve_skill_dir, download_skill_files_from_cloud
    except Exception as e:
        return {"skipped": f"skill file sync unavailable: {e}"}
    rows = _as_rows(send_get_agent_skills_request_to_cloud(*ctx))
    if rows is None:
        logger.warning("[cloud_hydrate] cloud skill list unavailable -- using the local skill folders")
        return {"error": "cloud skill list unavailable"}
    missing = []
    for sk in rows:
        src = str(sk.get("source") or "").strip().lower()
        if src in ("external", "subscribed") or not sk.get("name"):
            continue
        d = _resolve_skill_dir(sk)
        if d is None or not d.is_dir():
            missing.append(sk)
    if not missing:
        return {"downloaded": []}
    deadline = _time.monotonic() + wait_s
    threads = [threading.Thread(target=download_skill_files_from_cloud,
                                args=(sk,), kwargs={"trace_id": "hydrate", "wait_s": wait_s},
                                daemon=True) for sk in missing]
    for t in threads:
        t.start()
    for t in threads:
        t.join(max(0.0, deadline - _time.monotonic()))
    got = [sk["name"] for sk in missing if (_resolve_skill_dir(sk) or None) is not None
           and _resolve_skill_dir(sk).is_dir()]
    late = [sk["name"] for sk in missing if sk["name"] not in got]
    if late:
        logger.warning(f"[cloud_hydrate] skill files still downloading / unavailable: {late} "
                       f"-- they compile on the next start")
    return {"downloaded": got, "missing": late}


# ── the pass ─────────────────────────────────────────────────────────────

def hydrate_local_db_from_cloud(mainwin) -> Dict[str, Any]:
    """Fill the local database from the cloud copy. Never raises; returns what it did."""
    out: Dict[str, Any] = {"ok": False}
    db = getattr(mainwin, "ec_db_mgr", None)
    svc = getattr(db, "task_service", None)
    owner = str(getattr(mainwin, "user", "") or "")
    if svc is None or not owner:
        out["skipped"] = "no local database or no signed-in user"
        return out
    ctx = _cloud_ctx(mainwin)
    if ctx is None:
        out["skipped"] = "not signed in to the cloud"
        return out

    def _read(what, fn):
        try:
            rows = fn(ctx)
        except Exception as e:
            logger.warning(f"[cloud_hydrate] cloud {what} unavailable ({e}) -- using the local copy")
            return None
        if rows is None:
            logger.warning(f"[cloud_hydrate] cloud {what} query failed -- using the local copy")
        return rows

    # files first: prompts and skill folders (a task is useless without them)
    out["prompts"] = hydrate_prompts()
    try:
        out["skill_files"] = hydrate_skill_files(ctx)
    except Exception as e:
        logger.warning(f"[cloud_hydrate] skill files unavailable ({e}) -- using the local folders")

    agents = _read("agents", fetch_cloud_agents)
    tasks = _read("tasks", fetch_cloud_tasks)
    at_links = _read("agent-task links", fetch_cloud_agent_task_links)
    ts_links = _read("task-skill links", fetch_cloud_task_skill_links)

    from agent.db.models.association_models import DBAgentTaskRel, DBAgentTaskSkillRel
    try:
        with svc.session_scope() as s:
            if agents:
                out["agents_added"] = _persist_agents(s, agents, owner)
            if tasks:
                out["tasks"] = _persist_tasks(s, tasks, owner)
            if at_links:
                out["agent_task_links_added"] = _persist_links(
                    s, DBAgentTaskRel, at_links, "agent_id", "task_id")
            if ts_links:
                out["task_skill_links_added"] = _persist_links(
                    s, DBAgentTaskSkillRel, ts_links, "task_id", "skill_id",
                    {"role": "primary", "execution_order": 0, "is_required": True})
        out["ok"] = True
    except Exception as e:
        logger.warning(f"[cloud_hydrate] writing the cloud copy locally failed: {e}")
        out["error"] = str(e)
    out["cloud"] = {k: (None if v is None else len(v)) for k, v in
                    (("agents", agents), ("tasks", tasks),
                     ("agent_task_links", at_links), ("task_skill_links", ts_links))}
    logger.info(f"[cloud_hydrate] local database brought up to date from the cloud: {out}")
    return out
