#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fast Deploy Commands — generate the resources (agents, skills, tasks) for a
business scenario from a single config file.

    ecan deploy scenario -c config.json [-o result.json]

The config file is produced by the app's Fast Deploy panel and looks like:

    {
      "scenario": "douyin_cs",
      "config": { "store_id": "shop-a", "qa_agents": 6 }
    }

STATUS: `douyin_cs` performs REAL generation (shared-skill model — see
`_deploy_douyin_cs`); the remaining scenarios are stubbed plans that
validate the config, compute the resources they *would* create, and log
each step.
"""

import json
import os

import click

from ..base.output import get_output


def _tr(en: str, zh: str) -> str:
    """User-facing error/warning text in the app's language (Chinese on the CN
    build). The Fast Deploy panel shows these lines to the customer as-is."""
    try:
        from utils.app_env import is_cn
        return zh if is_cn() else en
    except Exception:
        return en


# ── Per-scenario recipes ─────────────────────────────────────────────────────
# Each recipe returns (plan: dict, log: list[str]) given the scenario config.
# `covered` marks recipes that are wired to real generation (none yet — all
# stubbed until the scenario resource graphs are finalized).

def _recipe_customer_service(scenario: str, cfg: dict):
    urls = cfg.get("store_urls") or []
    qa = int(cfg.get("qa_agents") or 6)
    log = [
        f"Scenario: {scenario}",
        f"Store URLs: {len(urls)}",
        f"Q&A agents: {qa}",
        f"[plan] 1 front-desk agent",
        f"[plan] {qa} Q&A agent(s)",
        f"[plan] 2 skills (front-desk dispatch, Q&A answering)",
        f"[plan] {1 + qa} task(s)",
    ]
    plan = {"agents": 1 + qa, "skills": 2, "tasks": 1 + qa}
    return plan, log


# The store platform each planned (not yet generating) scenario deploys to --
# a picked store must be of this platform.
_PLANNED_PLATFORMS = {"tmall_cs": "tmall"}

_RECIPES = {
    "douyin_cs": _recipe_customer_service,
    "douyin_cs_multi": _recipe_customer_service,
    "pdd_cs": _recipe_customer_service,
    "pdd_cs_multi": _recipe_customer_service,
    "tmall_cs": _recipe_customer_service,
}


# ── Real Douyin/抖店 customer-service deployment (shared-skill model) ────────
# SHARED_SKILL_MULTI_TASK_PLAN: the deployment REFERENCES the two published
# Feige skills (public / rentable / ¥0) instead of cloning per-agent copies:
#
#   skill_4f24592c81894ae7  飞鸽客服问答00  ← N Q&A tasks 飞鸽客服应答00N
#   skill_7f00760f659d4bc5  飞鸽客服前台01  ← 1 front-desk task 飞鸽客服前台001
#   (until 2026-10-04: skill_71209937ed7449bf 飞鸽客服前台00 -- replace mode still clears it)
#
# Their prompts (pr-287230 飞鸽客服应答0, pr-330448 飞鸽客服前台0) resolve
# under the skills' author (skill_owner); visibility of both prompts and both
# skills is verified up front — a miss aborts with a clear reason.
#
# The store URL is propagated as per-task variables (settings.task_vars:
# store_url / store_urls) — apply_task_vars seeds them into every run's
# prompt variables, so the prompts can reference {{store_url}}.
#
# Agents: N Q&A agents 客服小X (X drawn from a Chinese given-name pool) and
# one front-desk agent 前台小张, all under the Sales organization, pinned to
# this machine's vehicle so the affinity gate starts them here.

_DDCS_QA_PROMPT_ID = "pr-287230"     # 飞鸽客服应答0
_DDCS_FD_PROMPT_ID = "pr-330448"     # 飞鸽客服前台0
_DDCS_QA_SOCIAL_PROMPT_ID = "pr-543744"  # 飞鸽社交应答0
_DDCS_QA_RAG_PROMPT_ID = "pr-56931"      # 飞鸽RAG路由分类0
_DDCS_QA_SKILL_ID = "skill_4f24592c81894ae7"   # 飞鸽客服问答00
_DDCS_FD_SKILL_ID = "skill_7f00760f659d4bc5"   # 飞鸽客服前台01
_DDCS_FD_LEGACY_SKILL_ID = "skill_71209937ed7449bf"   # 飞鸽客服前台00, the front desk before 01
_DDCS_QA_SKILL_NAME = "飞鸽客服问答00"
_DDCS_FD_SKILL_NAME = "飞鸽客服前台01"
_DDCS_SALES_ORG_NAME = "Sales"

# Chinese given names for the Q&A agents (客服小X).
# ── Feige runtime env flags (the validated 抖店客服 run configuration).
# Written to <appdata>/run.env at deploy time; main.py loads that file at
# startup with override=False (a real OS env var always wins). Names are the
# canonical code spellings — several author-machine names were normalized
# (e.g. ECAN_LIVE_CHAT_* knobs are satisfied by their ECAN_FEIGE_* aliases
# via live_chat_env's site-alias fallback).
_DDCS_FEIGE_ENV = {
    "ECAN_FEIGE_WS": "1",
    "ECAN_FEIGE_WS_READER": "1",
    "ECAN_FEIGE_WS_SEND": "1",
    "ECAN_FEIGE_WS_SEND_RAW": "1",
    "ECAN_FEIGE_WS_SCRAPE": "1",
    "ECAN_FEIGE_WS_CAPTURE": "1",
    "ECAN_FEIGE_WS_CAPTURE_MAX_FRAMES": "5000",
    "ECAN_FEIGE_WS_COVERAGE": "1",
    "ECAN_FEIGE_WS_TRUST_EVENT": "1",
    "ECAN_FEIGE_WS_DIRECT_QA": "1",
    "ECAN_FEIGE_WS_STICKY_IDENTITY": "1",
    "ECAN_FEIGE_WS_PRIME_API": "1",
    "ECAN_FEIGE_WS_PAUSE_DOM_MONITOR": "1",
    "ECAN_FEIGE_WS_SKIP_TYPING_LOCK": "1",
    "ECAN_FEIGE_WS_NOROUTE_DIAG": "1",
    "ECAN_FEIGE_WS_RAW_DIAG": "1",
    "ECAN_FEIGE_WS_RAW_KEEPALIVE": "1",
    "ECAN_FEIGE_WS_RAW_KEEPALIVE_S": "20",
    "ECAN_FEIGE_WS_RAW_TOKEN_MAX_AGE": "300",
    "ECAN_FEIGE_WS_RECONNECT_FOLLOW": "1",
    "ECAN_FEIGE_WS_READ_ACK": "1",
    "ECAN_FEIGE_WS_READ_ACK_RAW": "1",
    "ECAN_FEIGE_WS_READ_ACK_DET_TAB": "1",
    "ECAN_FEIGE_WS_SEND_DET_TAB": "0",
    "ECAN_FEIGE_WS_SEND_DET_TAB_TRUST": "0",
    "ECAN_FEIGE_WS_SEND_INJECT_TIMEOUT_S": "6",
    "ECAN_FEIGE_WS_PLACEHOLDER_DET_TAB": "1",
    "ECAN_FEIGE_WS_CARD_PARSE": "1",
    "ECAN_FEIGE_WS_CARD_TRUST": "1",
    "ECAN_FEIGE_WS_CARD_DOM_DETAIL": "1",
    "ECAN_FEIGE_WS_CARD_FIRST_CONTACT": "0",
    "ECAN_FEIGE_WS_FIRST_CONTACT": "0",
    "ECAN_FEIGE_WS_FC_PRESUME": "0",
    "ECAN_FEIGE_WS_CAN_SEND_WIDE": "0",
    "ECAN_FEIGE_DEDICATED_CDP_LOOP": "1",
    "ECAN_FEIGE_DEDICATED_DETECTION_TAB": "1",
    "ECAN_FEIGE_LEAN_BASELINE": "0",
    "ECAN_FEIGE_TYPING_TAB_COUNT": "0",
    "ECAN_FEIGE_QA_MAX_CONCURRENCY": "3",
    "ECAN_FEIGE_HUMAN_MODE": "1",
    "ECAN_FEIGE_BOT_SUPPRESS": "1",
    "ECAN_FEIGE_BOT_TOGGLE_CAPTURE": "1",
    "ECAN_FEIGE_MT030_HANDOVER_OVERRIDE": "1",
    "ECAN_FEIGE_MT030_CARD_ACK_NOMASK": "1",
    "ECAN_FEIGE_SEND_RETRY_ON_EMPTY": "1",
    "ECAN_FEIGE_SEND_CDP_EVALUATE_TIMEOUT_S": "10",
    "ECAN_FEIGE_TIMEOUT_PRESUME_DELIVERED": "1",
    "ECAN_FEIGE_PLACEHOLDER_TIMEOUT_S": "6",
    "ECAN_FEIGE_DUMP_ON_MARSHAL_FAIL": "1",
    "ECAN_FEIGE_FC_FRAME_DUMP": "0",
    "ECAN_FEIGE_CARD_RESOLVE_WAIT": "1",
    "ECAN_FEIGE_CARD_SNF_FAILFAST": "1",
    "ECAN_FEIGE_PRODUCT_DETAIL_CAPTURE": "1",
    "ECAN_FEIGE_COLDSTART_RECOVERY_SCRAPE": "1",
    "ECAN_FEIGE_COLDSTART_RECOVERY_WINDOW_S": "45",
    "ECAN_FEIGE_STUCK_RECOVERY": "1",
    "ECAN_FEIGE_REOPEN_RECOVERY": "1",
    "ECAN_FEIGE_DORMANT_POLL": "1",
    "ECAN_FEIGE_UID_NAME_BRIDGE": "1",
    "ECAN_FEIGE_OPEN_CLAIM_CAPTURE": "1",
    "ECAN_FEIGE_OPEN_CLAIM_CAP_MAX": "5000",
    "ECAN_FEIGE_UNIFIED_BLOCKER_CLEAR": "1",
    "ECAN_FEIGE_FRONTDESK_PER_CUSTOMER_LOCK": "0",
    "ECAN_FEIGE_COOLDOWN_RENDERER_SLOW_SKIP": "1",
    "ECAN_FEIGE_BACKSTOP_INTERVAL_S": "5",
    "ECAN_FEIGE_BACKSTOP_STALE_S": "15",
    "ECAN_FEIGE_BACKSTOP_CONNECT_STALE_S": "4",
    "DIRECT_FEIGE_JOB_TIMEOUT_S": "15",
}


def _write_run_env(env_map: dict, log: list) -> None:
    """Merge *env_map* into <appdata>/run.env (loaded by main.py at startup).

    Keys already present in the file keep their existing values (a customer's
    hand-tuned override survives redeploys); only missing keys are appended.
    Best-effort: failures are logged, never abort the deploy.
    """
    import re as _re
    try:
        from config.envi import getECBotDataHome
        path = os.path.join(getECBotDataHome(), "run.env")
        existing_keys = set()
        lines = []
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                lines = f.read().splitlines()
            for line in lines:
                m = _re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
                if m:
                    existing_keys.add(m.group(1))
        added = [k for k in env_map if k not in existing_keys]
        if added:
            with open(path, "a", encoding="utf-8") as f:
                if not lines:
                    f.write("# eCan runtime env — loaded by main.py at startup (OS env wins).\n")
                f.write(f"# 抖店客服 Fast Deploy ({len(added)} flag(s))\n")
                for k in added:
                    f.write(f"{k}={env_map[k]}\n")
        # Current process too (harmless; CLI subprocess only)
        for k, v in env_map.items():
            os.environ.setdefault(k, v)
        log.append(
            f"Runtime env: {len(added)} new flag(s) written to {path} "
            f"({len(env_map) - len(added)} already present) — restart the app to apply."
        )
    except Exception as e:
        log.append(_tr(f"WARNING: run.env write failed ({e}) — set the Feige env flags manually.",
                       f"警告：写入 run.env 失败（{e}），请手动设置飞鸽运行参数。"))


_DDCS_QA_NAME_POOL = [
    "琳", "娜", "梅", "芳", "燕", "丽", "静", "敏", "慧", "娟",
    "霞", "玲", "红", "艳", "雪", "婷", "蕾", "欣", "悦", "洁",
    "璐", "薇", "晴", "岚", "楠", "萌", "彤", "菲", "露", "涵",
]


def _draw_qa_names(n: int) -> list:
    """n unique 名 from the pool; overflow gets a numeric suffix."""
    import random
    pool = list(_DDCS_QA_NAME_POOL)
    random.shuffle(pool)
    names = pool[:n]
    i = 0
    while len(names) < n:
        i += 1
        names.append(f"{pool[i % len(pool)]}{i}")
    return names


def _skill_author(row: dict) -> str:
    """The skill's original author (prompt-resolution identity)."""
    config = row.get("config") if isinstance(row.get("config"), dict) else {}
    return str(config.get("skill_owner") or row.get("owner") or "").strip()


def _prompt_visible(prompt_id: str, skill_owner: str, log: list) -> bool:
    """Whether *prompt_id* is visible to the runtime: present in the local
    prompt stores, or fetchable from the cloud under the skill author's
    partition (the same fallback the runtime prompt loader uses)."""
    if not _missing_system_prompts([prompt_id]):
        log.append(f"Prompt {prompt_id} found in local prompt store.")
        return True
    if skill_owner:
        try:
            from gui.ipc.w2p_handlers.prompt_cloud_sync import _get_cloud_context, _appsync_request
            cloud_ctx = _get_cloud_context()
            if cloud_ctx is None:
                # CLI subprocess: no MainWindow — the app's Fast Deploy
                # handler passes its auth token via env so the cloud
                # visibility check still works here.
                _cli_token = os.environ.get("ECAN_CLI_AUTH_TOKEN") or ""
                if _cli_token:
                    import requests as _rq
                    cloud_ctx = {"session": _rq.Session(), "token": _cli_token,
                                 "endpoint": None, "owner": ""}
            if cloud_ctx:
                query = """
                    query QueryPrompts($input: PromptQueryInput) {
                        queryPrompts(input: $input) { id owner }
                    }
                """
                resp = _appsync_request(query, cloud_ctx,
                                        variables={"input": {"id": prompt_id, "owner": skill_owner}})
                items = (resp.get("data") or {}).get("queryPrompts") or []
                if items:
                    log.append(f"Prompt {prompt_id} visible in cloud under skill owner {skill_owner}.")
                    return True
            else:
                log.append(f"Prompt {prompt_id}: no cloud context in CLI — cloud check skipped.")
        except Exception as e:
            log.append(f"Prompt {prompt_id}: cloud visibility check unavailable ({e}).")
    return False


def _company_root_org_id(ctx) -> str:
    """The company organization departments hang under ('' if there is none)."""
    try:
        rows = (ctx.db.org_service.get_all_orgs() or {}).get("data") or []
    except Exception:
        return ""
    roots = [r for r in rows if not r.get("parent_id") and r.get("org_type") == "company"]
    roots.sort(key=lambda r: (r.get("sort_order") or 0, str(r.get("created_at") or "")))
    return str(roots[0].get("id") or "") if roots else ""


def _ensure_sales_org(ctx, owner: str, log: list, name: str = _DDCS_SALES_ORG_NAME) -> str:
    """Return the id of organization *name* (Sales by default), creating it if absent."""
    result = ctx.db.org_service.search_orgs(name=name)
    rows = result.get("data") or [] if isinstance(result, dict) else []
    exact = [r for r in rows
             if str(r.get("name", "")).strip().lower() == name.lower()]
    if exact:
        org_id = exact[0].get("id")
        log.append(f"{name} organization found: {org_id}")
        return org_id
    data = {
        "name": name,
        "description": f"{name} organization (created by Fast Deploy)",
        "owner": owner,
    }
    # A department goes under the company root. Created parentless, it became
    # a second top-level organization and the Agents page stopped showing the
    # company's departments at the top (Operations, 2026-09-28).
    root_id = _company_root_org_id(ctx)
    if root_id:
        data.update({"parent_id": root_id, "org_type": "department", "level": 1})
    created = ctx.db.org_service.add_org(data)
    if not created.get("success"):
        raise RuntimeError(_tr(f"Could not find or create {name} organization: {created.get('error')}",
                                f"无法找到或创建部门（{name}）：{created.get('error')}"))
    org_id = created.get("id")
    log.append(f"{name} organization created: {org_id}")
    return org_id


def _missing_system_prompts(prompt_ids) -> list:
    """Ids among ``prompt_ids`` NOT present in the system prompts list —
    the same dirs the runtime prompt_loader searches: the per-user my_prompts
    store, the per-user subscribed_prompts store (where subscribe-time
    downloads of an AUTHOR's prompts land — a customer machine has the
    抖店客服 prompts ONLY here; v0.9.95q incident), plus the built-in
    sample_prompts. Scoped by ECAN_LOG_USER when this CLI runs as an app
    subprocess."""
    from pathlib import Path
    from utils.user_path_helper import get_log_user_data_dir, get_user_data_dir
    from agent.ec_skills.prompt_loader import SAMPLE_PROMPTS_DIR

    log_user = os.environ.get("ECAN_LOG_USER") or None

    def _dir(sub):
        # ECAN_LOG_USER is the exact dir name; only a username gets mapped.
        return Path(get_log_user_data_dir(log_user, sub) if log_user else get_user_data_dir(None, subdir=sub))
    user_dir = _dir("my_prompts")
    subscribed_dir = _dir("subscribed_prompts")
    have = set()
    for directory in (user_dir, subscribed_dir, Path(SAMPLE_PROMPTS_DIR)):
        if not directory.exists():
            continue
        for fp in directory.glob("*.json"):
            try:
                # Strict utf-8, exactly like the runtime prompt_loader: a
                # file it can't read must not count as "present" here.
                data = json.loads(fp.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(data, dict) and data.get("id"):
                have.add(data["id"])
    return [p for p in prompt_ids if p not in have]


def _load_system_skill(name: str):
    """Load a skill's diagram JSON from the system skills list — the user
    skill library (populated at app initialization) with the built-in
    resource skills as fallback. Returns None when absent from both."""
    from agent.ec_skills.extern_skills.extern_skills import (
        user_skills_root, resource_skills_root)
    dirname = name if name.endswith("_skill") else f"{name}_skill"
    for root in (user_skills_root(), resource_skills_root()):
        path = root / dirname / "diagram_dir" / f"{dirname}.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8-sig"))
    return None


def _task_store_id(row: dict) -> str:
    md = (row or {}).get("metadata")
    tv = md.get("task_vars") if isinstance(md, dict) else None
    return str((tv or {}).get("store_id") or "").strip() if isinstance(tv, dict) else ""


def _replace_cleanup(ctx, owner: str, skill_ids, log: list, store_id: str = "",
                     name_prefixes=()) -> dict:
    """Fast Deploy 'replace' mode: delete this owner's existing tasks that use
    the given (shared) skills FOR THIS STORE, and the agents serving only them
    — then the caller proceeds with a normal 'add'.

    Scoped by ``store_id`` (tasks with no store id when it is blank). It used
    to delete every task on these skills, so replacing store B wiped store A's
    agents too. An agent that still serves another store's task is kept.
    ``name_prefixes`` (when given) further limits it to tasks this platform's
    deploy named: platforms share the Q&A skill, so a Pinduoduo replace must
    not delete the Feige Q&A tasks. Other owners' rows are never touched.
    Returns {"tasks": [...], "agents": [...]}."""
    from ..base.sync import cloud_sync
    from agent.cloud_api.constants import DataType, Operation

    task_ids: list = []
    for sid in skill_ids:
        rels = ctx.db.task_service.get_tasks_by_skill(sid)
        for rel in (rels.get("data") or []) if isinstance(rels, dict) else []:
            tid = str((rel or {}).get("task_id") or "")
            if not tid or tid in task_ids:
                continue
            rows = (ctx.db.task_service.query_tasks(id=tid) or {}).get("data") or []
            if (rows and str(rows[0].get("owner") or "") == str(owner)
                    and _task_store_id(rows[0]) == store_id
                    and (not name_prefixes
                         or str(rows[0].get("name") or "").startswith(tuple(name_prefixes)))):
                task_ids.append(tid)

    agent_ids: list = []
    if task_ids:
        agents = (ctx.db.agent_service.get_agents_by_owner(owner) or {}).get("data") or []
        for a in agents:
            aid = str((a or {}).get("id") or "")
            if not aid:
                continue
            assoc = (ctx.db.agent_service.get_agent_task_associations(aid) or {}).get("data") or []
            linked = {str((x or {}).get("task_id") or "") for x in assoc} - {""}
            if linked & set(task_ids):
                if linked - set(task_ids):
                    log.append(f"Replace mode: kept agent {aid} -- it also serves tasks of another store")
                    continue
                agent_ids.append(aid)

    # Agents first (their task links go with them), then the tasks.
    for aid in agent_ids:
        r = ctx.db.agent_service.delete_agent(aid)
        if not (isinstance(r, dict) and r.get("success")):
            raise RuntimeError(_tr(f"replace: delete agent {aid} failed: {(r or {}).get('error')}",
                                    f"替换模式：删除智能体 {aid} 失败：{(r or {}).get('error')}"))
        cloud_sync(DataType.AGENT, {"id": aid}, Operation.DELETE)
    for tid in task_ids:
        r = ctx.db.task_service.delete_task(tid)
        if not (isinstance(r, dict) and r.get("success")):
            raise RuntimeError(_tr(f"replace: delete task {tid} failed: {(r or {}).get('error')}",
                                    f"替换模式：删除任务 {tid} 失败：{(r or {}).get('error')}"))
        cloud_sync(DataType.TASK, {"id": tid}, Operation.DELETE)

    log.append(f"Replace mode: deleted {len(agent_ids)} agent(s) and {len(task_ids)} task(s) "
               f"using the customer-service skills for store {store_id or '(none)'} (owner={owner})")
    return {"tasks": task_ids, "agents": agent_ids}


def _sync_created_to_cloud(ctx, created: dict, links: dict, log: list) -> None:
    """Push what the deploy created to the cloud: tasks, agents, then their links.

    The deploy only ever synced its DELETES, so a store staffed up on one
    machine never reached the cloud and another machine could never run it.
    Order matters -- a link needs both ends. Best-effort: a failed sync is
    counted and left to the offline queue; the local deployment stands.
    """
    try:
        from agent.cloud_api.constants import DataType, Operation
        from agent.cloud_api.offline_sync_manager import get_sync_manager
        manager = get_sync_manager()
    except Exception as e:
        log.append(f"Cloud sync skipped: {e}")
        return
    counts = {"synced": 0, "queued": 0, "failed": 0}

    def push(dtype, data):
        try:
            r = manager.sync_to_cloud(dtype, data, Operation.ADD) or {}
        except Exception:
            r = {}
        counts["synced" if r.get("synced") else "queued" if r.get("cached") else "failed"] += 1

    def row(service, rid):
        data = (service.query_tasks(id=rid) if service is ctx.db.task_service
                else service.query_agents(id=rid)) or {}
        rows = data.get("data") or []
        return rows[0] if rows else {"id": rid}

    for tid in created.get("tasks", []):
        push(DataType.TASK, row(ctx.db.task_service, tid))
    for aid in created.get("agents", []):
        push(DataType.AGENT, row(ctx.db.agent_service, aid))
    for aid, tid in links.get("agent_task", []):
        push(DataType.AGENT_TASK, {"agid": aid, "task_id": tid, "status": "assigned"})
    for tid, sid in links.get("task_skill", []):
        push(DataType.TASK_SKILL, {"task_id": tid, "skill_id": sid})
    log.append(f"Cloud sync: {counts['synced']} synced, {counts['queued']} queued for retry, "
               f"{counts['failed']} failed")


def _store_record(ctx, store_id: str, platform: str) -> dict:
    """The store's catalog record. Stores are created on the Stores page (name,
    platform, URLs); a deploy only staffs one, so an unknown store or one of
    another platform is refused before anything is changed."""
    svc = getattr(ctx.db, "store_service", None)
    if svc is None:
        raise RuntimeError(_tr("store catalog unavailable", "无法读取店铺列表"))
    rec = svc.get_store(store_id)
    if not rec:
        raise RuntimeError(_tr(f"store {store_id!r} is not in the store list -- create it on the Stores page first",
                                f"店铺 {store_id} 不在店铺列表中，请先在店铺页面创建"))
    from agent.ec_agents.store_catalog import normalize_platform
    plat = normalize_platform(rec.get("platform"))
    if plat and plat != normalize_platform(platform):
        raise RuntimeError(_tr(f"store {store_id!r} is a {plat} store, not {platform}",
                                f"店铺 {store_id} 属于 {plat} 平台，不是 {platform}"))
    return rec


# ── Live-chat customer-service platforms ────────────────────────────────────
# One deployment shape (a front desk per store + Q&A agents on shared skills),
# several platforms. A profile names what differs per platform.

from typing import NamedTuple


class _LiveChatProfile(NamedTuple):
    scenario: str
    label: str                    # shown in logs and task descriptions
    platform: str                 # store catalog platform key
    login_domain: str             # the site a store's login profile signs in to
    qa_skill_id: str
    qa_skill_name: str
    fd_skill_id: str
    fd_skill_name: str
    prompts: tuple                # ((prompt_id, name, "qa" | "fd"), ...)
    fd_task_prefix: str
    qa_task_prefix: str
    env_append: dict              # run.env keys added when missing (operator tuning survives)
    env_set: dict                 # run.env keys that must hold exactly this value
    find_skill_by_name: bool      # not yet published: local ids differ per machine
    fd_legacy_skill_ids: tuple = ()   # earlier front-desk skills: replace mode clears their tasks too


_DDCS_PROFILE = _LiveChatProfile(
    scenario="douyin_cs", label="抖店客服", platform="douyin", login_domain="im.jinritemai.com",
    qa_skill_id=_DDCS_QA_SKILL_ID, qa_skill_name=_DDCS_QA_SKILL_NAME,
    fd_skill_id=_DDCS_FD_SKILL_ID, fd_skill_name=_DDCS_FD_SKILL_NAME,
    prompts=((_DDCS_QA_PROMPT_ID, "飞鸽客服应答0", "qa"),
             (_DDCS_QA_SOCIAL_PROMPT_ID, "飞鸽社交应答0", "qa"),
             (_DDCS_QA_RAG_PROMPT_ID, "飞鸽RAG路由分类0", "qa"),
             (_DDCS_FD_PROMPT_ID, "飞鸽客服前台0", "fd")),
    fd_task_prefix="飞鸽客服前台", qa_task_prefix="飞鸽客服应答",
    env_append=_DDCS_FEIGE_ENV, env_set={}, find_skill_by_name=False,
    fd_legacy_skill_ids=(_DDCS_FD_LEGACY_SKILL_ID,),
)

# Pinduoduo (pdd_chat bundle). The bundle registers only when the process serves
# it (ECAN_LIVE_CHAT_SITE), which this deploy writes to run.env.
# The Q&A side is the Feige one (skill + prompts are platform-agnostic); only
# the front desk is Pinduoduo's own.
_PDD_PROFILE = _LiveChatProfile(
    scenario="pdd_cs", label="拼多多客服", platform="pinduoduo", login_domain="mms.pinduoduo.com",
    qa_skill_id=_DDCS_QA_SKILL_ID, qa_skill_name=_DDCS_QA_SKILL_NAME,
    fd_skill_id="skill_75261dd56d62457d", fd_skill_name="拼多多客服前台01",
    prompts=((_DDCS_QA_PROMPT_ID, "飞鸽客服应答0", "qa"),
             (_DDCS_QA_SOCIAL_PROMPT_ID, "飞鸽社交应答0", "qa"),
             (_DDCS_QA_RAG_PROMPT_ID, "飞鸽RAG路由分类0", "qa"),
             ("pr-920049", "拼多多客服前台0", "fd")),
    fd_task_prefix="拼多多客服前台", qa_task_prefix="拼多多客服应答",
    env_append={}, env_set={"ECAN_LIVE_CHAT_SITE": "pdd_chat"}, find_skill_by_name=True,
)

_LIVE_CHAT_PROFILES = {p.scenario: p for p in (_DDCS_PROFILE, _PDD_PROFILE)}


def _cleanup_skill_ids(profile: _LiveChatProfile) -> tuple:
    """Skills whose tasks 'replace' mode clears: the current pair plus any front
    desk this scenario used before (a store deployed on it would otherwise keep
    its old front desk running next to the new one)."""
    return (profile.fd_skill_id, profile.qa_skill_id) + tuple(profile.fd_legacy_skill_ids)
# "<scenario>_multi": several stores of one platform on this machine, one shared Q&A pool.
_MULTI_SUFFIX = "_multi"


def _set_run_env(env_map: dict, log: list) -> None:
    """Make each key in <appdata>/run.env hold exactly its value (replace or append).

    For switches whose value matters (the live-chat site) -- unlike
    ``_write_run_env``, which never overwrites an operator's tuning.
    """
    if not env_map:
        return
    import re as _re
    try:
        from config.envi import getECBotDataHome
        path = os.path.join(getECBotDataHome(), "run.env")
        lines = []
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                lines = f.read().splitlines()
        done = set()
        for i, line in enumerate(lines):
            m = _re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
            if m and m.group(1) in env_map:
                lines[i] = f"{m.group(1)}={env_map[m.group(1)]}"
                done.add(m.group(1))
        lines += [f"{k}={v}" for k, v in env_map.items() if k not in done]
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        for k, v in env_map.items():
            os.environ[k] = v
        log.append(f"Runtime env set: {', '.join(f'{k}={v}' for k, v in env_map.items())} "
                   f"— restart the app to apply.")
    except Exception as e:
        log.append(_tr(f"WARNING: run.env update failed ({e}) — set {sorted(env_map)} manually.",
                       f"警告：更新 run.env 失败（{e}），请手动设置 {sorted(env_map)}。"))


def _find_skill(ctx, profile: _LiveChatProfile, role: str):
    """The skill row for *role* ("qa" / "fd"): by id, then (unpublished skills) by exact name."""
    sid = profile.qa_skill_id if role == "qa" else profile.fd_skill_id
    name = profile.qa_skill_name if role == "qa" else profile.fd_skill_name
    r = ctx.db.skill_service.get_skill_by_id(sid)
    row = r.get("data") if isinstance(r, dict) and r.get("success") else None
    if row or not profile.find_skill_by_name:
        return row
    try:
        rows = (ctx.db.skill_service.query_skills(name=name) or {}).get("data") or []
    except Exception:
        rows = []
    exact = [x for x in rows if str(x.get("name") or "").strip() == name]
    return exact[0] if exact else None


def _verify_live_chat_assets(ctx, profile: _LiveChatProfile, log: list) -> dict:
    """{"qa": row, "fd": row} after checking both skills and every prompt are visible."""
    from utils.logger_helper import logger_helper as logger
    rows = {}
    for role in ("qa", "fd"):
        row = _find_skill(ctx, profile, role)
        sname = profile.qa_skill_name if role == "qa" else profile.fd_skill_name
        sid = profile.qa_skill_id if role == "qa" else profile.fd_skill_id
        if not row:
            msg = _tr(f"Skill {sname} ({sid}) is not visible — subscribe to it in the "
                      f"skill store (public / rentable / ¥0) and retry.",
                      f"看不到技能 {sname}（{sid}）：请在技能商店订阅该技能后重试。")
            logger.error(f"[FastDeploy][{profile.scenario}] {msg}")
            raise RuntimeError(msg)
        rows[role] = row
    log.append(f"Skills verified: {profile.qa_skill_name} ({rows['qa'].get('id') or profile.qa_skill_id}), "
               f"{profile.fd_skill_name} ({rows['fd'].get('id') or profile.fd_skill_id})")
    for pid, pname, role in profile.prompts:
        if not _prompt_visible(pid, _skill_author(rows[role]), log):
            msg = _tr(f"Prompt {pname} ({pid}) is not visible — it should come with "
                      f"the subscribed skill {rows[role].get('name')}; re-subscribe "
                      f"or sync prompts and retry.",
                      f"看不到提示词 {pname}（{pid}）：它应随已订阅的技能 "
                      f"{rows[role].get('name')} 一起下载，请重新订阅或同步提示词后重试。")
            logger.error(f"[FastDeploy][{profile.scenario}] {msg}")
            raise RuntimeError(msg)
    log.append("Prompts verified: " + ", ".join(f"{n} ({p})" for p, n, _ in profile.prompts))
    return rows


def _ensure_account_api_key(log: list, scenario: str) -> None:
    """Make sure the account has an API key (create when absent). Best-effort:
    the runtime doesn't hard-require it yet, so a failure only warns."""
    from utils.logger_helper import logger_helper as logger
    try:
        _cli_token = (os.environ.get("ECAN_CLI_AUTH_TOKEN") or "").strip()
        if _cli_token:
            from agent.cloud_api.api_keys import ensure_api_key, mask_api_key
            _key_result = ensure_api_key(_cli_token)
            _key = _key_result.get("apiKey")
            if _key:
                log.append(
                    f"API key {'created' if _key_result.get('created') else 'exists'}: "
                    f"{mask_api_key(_key)}"
                )
            else:
                log.append(f"API key check failed (non-fatal): "
                           f"{_key_result.get('message') or _key_result.get('error')}")
        else:
            log.append("API key check skipped: no ECAN_CLI_AUTH_TOKEN in environment")
    except Exception as _key_err:
        logger.warning(f"[FastDeploy][{scenario}] API key ensure failed (non-fatal): {_key_err}")
        log.append(f"API key check failed (non-fatal): {_key_err}")


def _local_vehicle(owner: str, log: list):
    """This machine's verified vehicle id, or None (never an arbitrary DB row:
    v0.9.95t pinned every agent to a stale vehicle and all were skipped)."""
    try:
        from agent.ec_agents.vehicle_affinity import resolve_local_vehicle_id
        return resolve_local_vehicle_id(username=os.environ.get("ECAN_LOG_USER") or owner) or None
    except Exception as e:
        log.append(_tr(f"WARNING: local vehicle id resolution failed ({e}).",
                       f"警告：无法识别本机设备编号（{e}）。"))
        return None


def _store_vehicle(store_id: str, owner: str, log: list):
    """The machine a store's agents are assigned to: the store's cloud
    assignment (live, else the app's last cached copy), else this machine."""
    try:
        from types import SimpleNamespace
        from config.envi import getECBotDataHome
        from agent.ec_agents import store_placement
        log_user = os.environ.get("ECAN_LOG_USER") or ""
        home = os.path.join(getECBotDataHome(), log_user) if log_user else ""
        snap = store_placement.refresh(SimpleNamespace(my_ecb_data_homepath=home)) or {}
        assigned = ((snap.get("stores") or {}).get(store_id) or {}).get("assigned")
        if assigned:
            log.append(f"Placement: store {store_id!r} is assigned to vehicle {assigned}; its agents follow it")
            return assigned
    except Exception as e:
        log.append(f"Placement: store {store_id!r} assignment unreadable ({e}); using this machine")
    vid = _local_vehicle(owner, log)
    log.append(f"Placement: store {store_id!r} unassigned; its agents go to this machine ({vid or 'unknown'})")
    return vid


class _Builder:
    """Creates tasks and agents for one deployment and remembers what it made."""

    def __init__(self, ctx, owner: str, org_id: str, label: str):
        self.ctx, self.owner, self.org_id, self.label = ctx, owner, org_id, label
        self.created = {"skills": [], "tasks": [], "agents": []}
        self.links = {"task_skill": [], "agent_task": []}

    def task(self, name: str, skill_id: str, task_vars: dict, identity: dict | None = None,
             trigger: str = "auto", schedule: dict | None = None) -> str:
        settings = {"task_vars": dict(task_vars)}
        if identity:
            settings["browser_identity"] = dict(identity)
        row = {
            "name": name, "owner": self.owner, "source": "fast_deploy",
            "description": f"{self.label} — Fast Deploy (shared skill)",
            "task_type": "browser_automation", "trigger": trigger, "status": "pending",
            "settings": settings,
        }
        if schedule:
            row["schedule"] = dict(schedule)
        tr = self.ctx.db.task_service.add_task(row)
        if not tr.get("success"):
            raise RuntimeError(_tr(f"add_task({name}) failed: {tr.get('error')}",
                                    f"创建任务 {name} 失败：{tr.get('error')}"))
        tid = tr.get("id")
        self.created["tasks"].append(tid)
        link = self.ctx.db.task_service.add_skill_to_task(tid, skill_id, role="primary")
        self.links["task_skill"].append((tid, skill_id))
        if not (isinstance(link, dict) and link.get("success")):
            raise RuntimeError(_tr(f"link task {name} → skill {skill_id} failed: {(link or {}).get('error')}",
                                    f"将任务 {name} 关联到技能 {skill_id} 失败：{(link or {}).get('error')}"))
        return tid

    def agent(self, name: str, skill_id: str, task_id: str, vehicle_id=None) -> str:
        adata = {"name": name, "description": f"{self.label} — Fast Deploy (shared skill)",
                 "skills": [skill_id], "org_id": self.org_id}
        # Task links must not depend on vehicle resolution: without them the
        # agents exist but never run their tasks.
        if task_id:
            adata["tasks"] = [task_id]
        if vehicle_id:
            adata["vehicle_id"] = vehicle_id
        ar = self.ctx.db.agent_service.create_agent_from_data(adata, self.owner)
        if not ar.get("success"):
            raise RuntimeError(_tr(f"create agent {name} failed: {ar.get('error')}",
                                    f"创建智能体 {name} 失败：{ar.get('error')}"))
        aid = ar.get("id")
        self.created["agents"].append(aid)
        if task_id:
            self.links["agent_task"].append((aid, task_id))
        return aid


def _deploy_douyin_cs(cfg: dict, ctx, owner: str):
    """The 抖店客服 deployment (Feige). Kept by name for callers and tests."""
    return _deploy_live_chat(cfg, ctx, owner, _DDCS_PROFILE)


def _deploy_live_chat(cfg: dict, ctx, owner: str, profile: _LiveChatProfile = _DDCS_PROFILE):
    """Create one store's live-chat CS deployment (shared-skill model).
    Returns (plan, log, created). Raises on hard failure — the caller turns
    that into the failure result the Fast Deploy panel pops."""
    from utils.logger_helper import logger_helper as logger

    qa_n = int(cfg.get("qa_agents") or 8)  # matches the panel default
    log = []

    # ── Store identity. NOT derivable from the URL: every seller of a platform
    #    shares one workstation URL, so resolve_store_id's URL fallback returns
    #    the same constant for every store. Without an id a second store's
    #    per-store settings and metering would silently merge into the first.
    store_id = str(cfg.get("store_id") or "").strip()
    if not store_id:
        raise RuntimeError(_tr("store_id is required -- pick a store (create it on the Stores page first)",
                                "请选择店铺（请先在店铺页面创建）"))
    rec = _store_record(ctx, store_id, profile.platform)
    store_urls = _store_urls_of(rec)
    if not store_urls:
        raise RuntimeError(_tr(f"store {store_id!r} has no URL -- add it on the Stores page",
                                f"店铺 {store_id} 没有设置链接，请在店铺页面添加"))

    # ── 0) 'replace' mode: clear THIS STORE's previous deployment first.
    if str(cfg.get("mode") or "add").strip().lower() == "replace":
        _replace_cleanup(ctx, owner, _cleanup_skill_ids(profile), log,
                         store_id=store_id,
                         name_prefixes=(profile.fd_task_prefix, profile.qa_task_prefix))
    else:
        log.append("Add mode: existing tasks/agents kept")

    # ── 1+2) Visibility: both skills, then their prompts (prompt visibility
    #    rides the skills' author identity).
    rows = _verify_live_chat_assets(ctx, profile, log)
    qa_skill_id = rows["qa"].get("id") or profile.qa_skill_id
    fd_skill_id = rows["fd"].get("id") or profile.fd_skill_id

    _ensure_account_api_key(log, profile.scenario)

    # ── Store URL propagation: per-task variables. apply_task_vars seeds
    #    these into every run's prompt variables ({{store_url}} / {{store_urls}}).
    task_vars = {"store_url": store_urls[0], "store_urls": ",".join(store_urls)}
    log.append(f"Task variables: store_url={store_urls[0]} (+{len(store_urls) - 1} more)"
               if len(store_urls) > 1 else f"Task variables: store_url={store_urls[0]}")

    task_vars["store_id"] = store_id
    log.append(f"Store id: {store_id}")

    # ── Placement: a store's agents go to the vehicle the STORE is assigned
    #    to (by default this machine), never to whichever machine deployed.
    vehicle_id = _store_vehicle(store_id, owner, log)

    org_id = _ensure_sales_org(ctx, owner, log)

    # The store's login: its tasks run in its own browser profile (created
    # when it has none), so a second store never drives the first one's
    # logged-in browser (build_helpers.browser_type_for_identity). Local only
    # -- the profile never syncs.
    rec = {**rec, "store_id": store_id, "name": rec.get("name") or store_id}
    identity, needs = _ensure_store_login(ctx, rec, profile.login_domain, log)
    log.append(f"Browser: store {store_id!r} runs in its own login profile "
               f"{identity['browser_profile_id']!r}")
    needs_login = ([{"store_id": store_id, "store_name": rec["name"],
                     "profile_id": identity["browser_profile_id"]}] if needs else [])
    if needs_login:
        log.append(f"Sign store {rec['name']!r} in once (Settings → Browser Profiles → Launch): "
                   f"{identity['browser_profile_id']}")
    b = _Builder(ctx, owner, org_id, profile.label)

    def _add_task(name: str, skill_id: str, extra_vars: dict | None = None) -> str:
        tvars = dict(task_vars)
        if extra_vars:
            tvars.update(extra_vars)
        settings = {"task_vars": tvars}
        if identity:
            settings["browser_identity"] = dict(identity)
        return b.task(name, skill_id, settings["task_vars"], settings.get("browser_identity"))

    # ── Runtime env → <appdata>/run.env (applied on next app start).
    if profile.env_append:
        _write_run_env(profile.env_append, log)
    _set_run_env(profile.env_set, log)

    # ── Front-desk task + agent FIRST: the Q&A tasks carry the front-desk
    #    agent's id in task_vars -- the shared Q&A skill's pend_event filters on
    #    {{front_desk_agent_id}}, resolved from task_vars at task launch.
    fd_name = f"{profile.fd_task_prefix}001"
    fd_task_id = _add_task(fd_name, fd_skill_id)
    fd_agent_id = b.agent("前台小张", fd_skill_id, fd_task_id, vehicle_id)
    log.append(f"Created task {fd_name} → {profile.fd_skill_name}")
    log.append(f"Created front-desk agent 前台小张 ({fd_agent_id}, org=Sales)")

    qa_task_ids = []
    for i in range(1, qa_n + 1):
        qa_task_ids.append(_add_task(f"{profile.qa_task_prefix}{i:03d}", qa_skill_id,
                                     extra_vars={"front_desk_agent_id": fd_agent_id}))
    for name, tid in zip(_draw_qa_names(qa_n), qa_task_ids):
        b.agent(f"客服小{name}", qa_skill_id, tid, vehicle_id)
    log.append(f"Created {qa_n} Q&A task(s) {profile.qa_task_prefix}001..{qa_n:03d} → "
               f"{profile.qa_skill_name} (task_vars.front_desk_agent_id={fd_agent_id})")
    log.append(f"Created {qa_n} Q&A agent(s) 客服小X (org=Sales)")

    plan = {"agents": len(b.created["agents"]), "skills": 0, "tasks": len(b.created["tasks"]),
            "needs_login": needs_login}
    logger.info(
        f"[FastDeploy][{profile.scenario}] SUCCESS: {plan['agents']} agent(s), {plan['tasks']} task(s) "
        f"referencing shared skills {qa_skill_id}/{fd_skill_id}; "
        f"store_url + front_desk_agent_id propagated via task_vars"
    )
    created, links = b.created, b.links
    _sync_created_to_cloud(ctx, created, links, log)
    return plan, log, created


# ── Several stores on this machine, one shared Q&A pool ─────────────────────

def _login_profile_id(store_id: str) -> str:
    """A profile id for a store's login: the registry allows [A-Za-z0-9_-] only,
    and store ids are often Chinese, so keep what fits plus a short hash."""
    import hashlib
    import re as _re
    base = _re.sub(r"[^A-Za-z0-9_-]", "", store_id)[:40].strip("-_")
    digest = hashlib.sha1(store_id.encode("utf-8")).hexdigest()[:8]
    return f"{base}-{digest}-login" if base else f"store-{digest}-login"


def _store_urls_of(rec: dict) -> list:
    urls = rec.get("store_urls") or []
    if isinstance(urls, str):
        try:
            urls = json.loads(urls)
        except Exception:
            urls = [u for u in urls.split(",") if u.strip()]
    return [str(u).strip() for u in urls if str(u).strip()]


def _profile_registry():
    from agent.ec_skills.browser_use_extension.fingerprint import profile_registry
    return profile_registry


def _ensure_store_login(ctx, rec: dict, login_domain: str, log: list):
    """(browser identity, needs_login) for one store -- creating its login profile if it has none.

    A store with no profile of its own would run in the shared default browser,
    and one browser keeps only ONE store's customer-service page online. The
    profile starts empty: someone signs the store in once (Settings -> Browser
    Profiles -> Launch). Profiles stay on this machine.
    """
    reg = _profile_registry()
    store_id = rec["store_id"]
    pid = str(rec.get("browser_profile_id") or "").strip()
    if pid and reg.get_profile(pid):
        state = (reg.login_state(pid) or {}).get("state")
        return {"browser_profile_id": pid}, state != reg.LOGIN_OK
    if not pid:
        pid = _login_profile_id(store_id)
    if not reg.get_profile(pid):
        prof = reg.make_profile(pid, label=f"{rec.get('name') or store_id}",
                                domain_name=login_domain, locale="zh-CN", store_id=store_id)
        reg.save_profile(prof)
        log.append(f"Login profile {pid!r} created for store {store_id!r} (sign it in once)")
    try:
        ctx.db.store_service.upsert_store({"store_id": store_id, "browser_profile_id": pid})
    except Exception as e:
        log.append(f"Store {store_id!r}: login profile not recorded on the store ({e})")
    return {"browser_profile_id": pid}, True


def _deploy_live_chat_multi(cfg: dict, ctx, owner: str, profile: _LiveChatProfile):
    """Several stores of one platform on this machine.

    Per store: its own login profile (created when missing), a front desk task
    carrying ``store_id`` + that browser identity, and a front-desk agent that
    follows the store's placement. Shared: ONE pool of Q&A agents serving every
    store's front desk -- each Q&A task accepts all of them
    (``front_desk_agent_id`` = comma list, a membership filter at launch) and
    answers whichever one asked (send_chat's recipient is back-filled from the
    event sender). The pool is pinned to this machine.
    """
    from utils.logger_helper import logger_helper as logger

    store_ids = []
    for x in cfg.get("stores") or []:
        sid = str((x.get("store_id") if isinstance(x, dict) else x) or "").strip()
        if sid and sid not in store_ids:
            store_ids.append(sid)
    if not store_ids:
        raise RuntimeError(_tr("pick at least one store", "请至少选择一个店铺"))
    qa_n = int(cfg.get("qa_agents") or 4)
    if qa_n < 1:
        raise RuntimeError(_tr("at least one Q&A agent is needed", "至少需要一个问答客服"))
    log = [f"Stores: {', '.join(store_ids)}; shared Q&A agents: {qa_n}"]

    recs = [_store_record(ctx, sid, profile.platform) for sid in store_ids]

    if str(cfg.get("mode") or "add").strip().lower() == "replace":
        prefixes = (profile.fd_task_prefix, profile.qa_task_prefix)
        for sid in store_ids:
            _replace_cleanup(ctx, owner, _cleanup_skill_ids(profile), log, store_id=sid,
                             name_prefixes=prefixes)
        # the previous shared pool (its tasks carry no store id)
        _replace_cleanup(ctx, owner, (profile.qa_skill_id,), log, store_id="", name_prefixes=prefixes)
    else:
        log.append("Add mode: existing tasks/agents kept")

    rows = _verify_live_chat_assets(ctx, profile, log)
    qa_skill_id = rows["qa"].get("id") or profile.qa_skill_id
    fd_skill_id = rows["fd"].get("id") or profile.fd_skill_id
    _ensure_account_api_key(log, profile.scenario)

    vehicle_id = _local_vehicle(owner, log)
    if not vehicle_id:
        log.append(_tr("WARNING: no local vehicle id — the shared Q&A pool is UNPINNED (it may start on other machines too).",
                        "警告：无法识别本机设备编号，共享问答客服未绑定到本机（可能也会在其他电脑上启动）。"))
    org_id = _ensure_sales_org(ctx, owner, log)
    if profile.env_append:
        _write_run_env(profile.env_append, log)
    _set_run_env(profile.env_set, log)

    b = _Builder(ctx, owner, org_id, profile.label)
    fd_ids, needs_login = [], []
    for rec in recs:
        sid = rec["store_id"]
        name = str(rec.get("name") or sid)
        urls = _store_urls_of(rec)
        identity, needs = _ensure_store_login(ctx, rec, profile.login_domain, log)
        if needs:
            needs_login.append({"store_id": sid, "store_name": name,
                                "profile_id": identity["browser_profile_id"]})
        tvars = {"store_id": sid}
        if urls:
            tvars.update(store_url=urls[0], store_urls=",".join(urls))
        tid = b.task(f"{profile.fd_task_prefix}-{name}", fd_skill_id, tvars, identity)
        # A store's agent goes to the vehicle the store is assigned to.
        aid = b.agent(f"前台-{name}", fd_skill_id, tid, _store_vehicle(sid, owner, log))
        fd_ids.append(aid)
        log.append(f"Store {name!r}: front desk {aid} in login profile {identity['browser_profile_id']!r}")

    senders = ",".join(fd_ids)
    for i, qa_name in zip(range(1, qa_n + 1), _draw_qa_names(qa_n)):
        tid = b.task(f"{profile.qa_task_prefix}共享{i:03d}", qa_skill_id,
                     {"front_desk_agent_id": senders})
        b.agent(f"客服小{qa_name}", qa_skill_id, tid, vehicle_id)
    log.append(f"Created a shared pool of {qa_n} Q&A agent(s) serving {len(fd_ids)} front desk(s)")
    if needs_login:
        log.append("Sign these stores in once (Settings → Browser Profiles → Launch): "
                   + ", ".join(f"{x['store_name']} ({x['profile_id']})" for x in needs_login))

    plan = {"agents": len(b.created["agents"]), "skills": 0, "tasks": len(b.created["tasks"]),
            "stores": len(recs), "needs_login": needs_login}
    logger.info(f"[FastDeploy][{profile.scenario}_multi] SUCCESS: {len(recs)} store(s), "
                f"{plan['agents']} agent(s), {plan['tasks']} task(s); {len(needs_login)} need a login")
    _sync_created_to_cloud(ctx, b.created, b.links, log)
    return plan, log, b.created


# ── Store operations (运营): one agent per role, on the platform's role skills ──
# Each role runs the skill named exactly <platform>_<role>_0. After-sales runs
# on the schedule chosen in the panel (processing orders and messages); the
# other roles start on a chat message, so the manager (or the owner, in chat)
# decides when they work.

_OPS_PLATFORMS = {
    "amazon_ops": ("amazon", "亚马逊", "Amazon"),
    "ebay_ops": ("ebay", "eBay", "eBay"),
    "etsy_ops": ("etsy", "Etsy", "Etsy"),
    "shopify_ops": ("shopify", "Shopify", "Shopify"),
    "tiktok_ops": ("tiktok", "TikTok", "TikTok"),
}

# (role, 中文, English); manage last -- its task carries the others' agent ids.
_OPS_ROLES = (
    ("after_sales", "售后", "After-sales"),
    ("pre_sales", "售前", "Pre-sales"),
    ("sales", "销售", "Sales"),
    ("marketing", "营销", "Marketing"),
    ("procurement", "采购", "Procurement"),
    ("research", "调研", "Research"),
    ("manage", "经理", "Manager"),
)
_OPS_ORG_NAME = "Operations"
_OPS_SCHEDULE_UNITS = ("minutes", "hours", "days")


def _find_skill_by_exact_name(ctx, name: str):
    try:
        rows = (ctx.db.skill_service.query_skills(name=name) or {}).get("data") or []
    except Exception:
        rows = []
    exact = [x for x in rows if str(x.get("name") or "").strip() == name]
    return exact[0] if exact else None


def _ops_schedule(cfg: dict) -> dict:
    """The after-sales task's schedule (same shape the Tasks page saves)."""
    sch = cfg.get("schedule") if isinstance(cfg.get("schedule"), dict) else {}
    start = str(sch.get("start") or "").strip()
    unit = str(sch.get("unit") or "").strip().lower()
    try:
        every = int(sch.get("every") or 0)
    except (TypeError, ValueError):
        every = 0
    if not start or every < 1 or unit not in _OPS_SCHEDULE_UNITS:
        raise RuntimeError(_tr("the after-sales schedule needs a start time and a repeat interval",
                               "请设置售后任务的开始时间和执行间隔"))
    return {
        "repeat_type": f"by {unit}", "repeat_number": every, "repeat_unit": f"by {unit}",
        "start_date_time": start, "end_date_time": None, "time_out": 3600,
    }


def _deploy_operations(cfg: dict, ctx, owner: str, scenario_key: str):
    """One store's operations team: a task + agent per role skill. Returns (plan, log, created)."""
    from urllib.parse import urlparse
    from utils.logger_helper import logger_helper as logger

    platform, plat_zh, plat_en = _OPS_PLATFORMS[scenario_key]
    label = _tr(f"{plat_en} operations", f"{plat_zh}运营")
    log = []

    store_id = str(cfg.get("store_id") or "").strip()
    if not store_id:
        raise RuntimeError(_tr("store_id is required -- pick a store (create it on the Stores page first)",
                                "请选择店铺（请先在店铺页面创建）"))
    rec = _store_record(ctx, store_id, platform)
    store_urls = _store_urls_of(rec)
    if not store_urls:
        raise RuntimeError(_tr(f"store {store_id!r} has no URL -- add it on the Stores page",
                                f"店铺 {store_id} 没有设置链接，请在店铺页面添加"))
    store_name = str(rec.get("name") or store_id)
    schedule = _ops_schedule(cfg)

    # Every role skill must exist BEFORE anything is created.
    skills, missing = {}, []
    for role, _zh, _en in _OPS_ROLES:
        name = f"{platform}_{role}_0"
        row = _find_skill_by_exact_name(ctx, name)
        if row:
            skills[role] = row
        else:
            missing.append(name)
    if missing:
        raise RuntimeError(_tr(
            f"missing skills: {', '.join(missing)} -- subscribe to or create them, then retry",
            f"缺少技能：{', '.join(missing)}，请先订阅或创建这些技能后重试"))
    log.append("Skills verified: " + ", ".join(f"{r['name']} ({r.get('id')})" for r in skills.values()))

    _ensure_account_api_key(log, scenario_key)
    org_id = _ensure_sales_org(ctx, owner, log, name=_OPS_ORG_NAME)
    rec = {**rec, "store_id": store_id, "name": store_name}
    identity, needs = _ensure_store_login(ctx, rec, urlparse(store_urls[0]).hostname or "", log)
    needs_login = ([{"store_id": store_id, "store_name": store_name,
                     "profile_id": identity["browser_profile_id"]}] if needs else [])
    store_vehicle = _store_vehicle(store_id, owner, log)

    base_vars = {"store_id": store_id, "store_url": store_urls[0], "store_urls": ",".join(store_urls)}
    b = _Builder(ctx, owner, org_id, label)
    agent_ids = {}
    for role, zh, en in _OPS_ROLES:
        skill_id = skills[role].get("id")
        tvars = dict(base_vars)
        if role == "manage":
            # The manager messages the others: give its prompt their agent ids.
            tvars.update({f"{r}_agent_id": aid for r, aid in agent_ids.items()})
        role_name = _tr(en, zh)
        if role == "after_sales":
            tid = b.task(f"{plat_zh}{zh}-{store_name}", skill_id, tvars, identity,
                         trigger="schedule", schedule=schedule)
        else:
            tid = b.task(f"{plat_zh}{zh}-{store_name}", skill_id, tvars, identity, trigger="message")
        agent_ids[role] = b.agent(f"{store_name}-{role_name}", skill_id, tid, store_vehicle)
        log.append(f"Created {role_name}: task {tid} → {skills[role].get('name')}, agent {agent_ids[role]}"
                   + (f" (every {schedule['repeat_number']} {schedule['repeat_type'][3:]} "
                      f"from {schedule['start_date_time']})" if role == "after_sales" else " (starts on a chat message)"))
    if needs_login:
        log.append(_tr(f"Sign store {store_name!r} in once (Settings → Browser Profiles → Launch): "
                       f"{identity['browser_profile_id']}",
                       f"请先登录店铺 {store_name}（设置 → 浏览器配置 → 启动）：{identity['browser_profile_id']}"))

    plan = {"agents": len(b.created["agents"]), "skills": 0, "tasks": len(b.created["tasks"]),
            "needs_login": needs_login}
    logger.info(f"[FastDeploy][{scenario_key}] SUCCESS: {plan['agents']} agent(s), "
                f"{plan['tasks']} task(s) for store {store_id!r}")
    _sync_created_to_cloud(ctx, b.created, b.links, log)
    return plan, log, b.created


@click.group()
def deploy():
    """
    Fast Deploy — scaffold resources for a business scenario.

    Examples:
      ecan deploy scenario -c fast_deploy.json
      ecan deploy scenario -c fast_deploy.json -o result.json
    """
    pass


@deploy.command('scenario')
@click.option('--config', '-c', required=True, type=click.Path(exists=True),
              help='Scenario config JSON produced by the Fast Deploy panel.')
@click.option('--output', '-o', type=click.Path(),
              help='Write the JSON result to this file (for programmatic callers).')
def scenario(config, output):
    """
    Generate resources for a business scenario from a config file.

    OPERATION command. Reads {scenario, config}, runs the scenario recipe,
    and reports the resources created (currently a stubbed plan).
    """
    out = get_output()

    def _emit(result: dict, ok: bool):
        if output:
            try:
                with open(output, 'w', encoding='utf-8') as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)
            except Exception as e:  # never crash on the side-channel write
                out.warning(f"Could not write result file: {e}")
        try:
            out.json(result)
        except Exception:
            click.echo(json.dumps(result, ensure_ascii=False))
        if not ok:
            raise SystemExit(1)

    try:
        with open(config, 'r', encoding='utf-8') as f:
            payload = json.load(f)
    except Exception as e:
        _emit({"status": "failure", "message": _tr(f"Invalid config file: {e}", f"配置文件无效：{e}"), "log": []}, ok=False)
        return

    scenario_key = str(payload.get("scenario") or "").strip()
    cfg = payload.get("config") or {}
    recipe = _RECIPES.get(scenario_key)

    if not recipe and scenario_key not in _OPS_PLATFORMS:
        _emit({
            "status": "failure",
            "scenario": scenario_key,
            "message": _tr(f"Unknown scenario: {scenario_key!r}", f"未知的场景：{scenario_key}"),
            "log": [f"No recipe registered for {scenario_key!r}"],
        }, ok=False)
        return

    base_key = scenario_key[:-len("_multi")] if scenario_key.endswith("_multi") else scenario_key
    is_multi = scenario_key.endswith("_multi")
    urls = cfg.get("store_urls") or []
    if is_multi or base_key in _LIVE_CHAT_PROFILES or base_key in _OPS_PLATFORMS:
        urls = urls or ["(from each store's record)"]   # these deploys read URLs off the stores
    elif not urls and str(cfg.get("store_id") or "").strip():
        # A store picked in the panel: its URLs are on its record (Stores page).
        try:
            from ..base.context import get_context
            rec = _store_record(get_context(), str(cfg["store_id"]).strip(),
                                _PLANNED_PLATFORMS.get(scenario_key, ""))
        except Exception as e:
            _emit({"status": "failure", "scenario": scenario_key,
                   "message": str(e), "log": [_tr(f"Validation failed: {e}", f"校验失败：{e}")]}, ok=False)
            return
        urls = cfg["store_urls"] = _store_urls_of(rec)
    if not isinstance(urls, list):
        _emit({
            "status": "failure",
            "scenario": scenario_key,
            "message": _tr("store_urls must be a list of URLs.", "店铺链接格式不正确"),
            "log": ["Validation failed: store_urls is not a list"],
        }, ok=False)
        return
    if not urls:
        _emit({
            "status": "failure",
            "scenario": scenario_key,
            "message": _tr("At least one store URL is required.", "请至少提供一个店铺链接（在店铺页面设置）"),
            "log": ["Validation failed: store_urls is empty"],
        }, ok=False)
        return

    # Real deployments: live-chat customer service (抖店 / 拼多多), one store
    # or several with a shared Q&A pool. The other scenarios are stubbed plans.
    if base_key in _LIVE_CHAT_PROFILES:
        profile = _LIVE_CHAT_PROFILES[base_key]
        from ..base.context import get_context
        ctx = get_context()
        owner = ctx.username or os.environ.get("ECAN_DEPLOY_OWNER") or "default"
        # Chrome environment first (install check with download link, PATH,
        # desktop-shortcut debug flags) — the 2026-09-04/05 customer runs
        # failed before detection ever started because eCan attached to a
        # Chrome without the Feige page. See cli/deploy/chrome_precheck.py.
        from .chrome_precheck import run_chrome_precheck
        try:
            pre_ok, pre_log, pre_msg = run_chrome_precheck()
        except Exception as e:  # never let the check itself block a deploy
            pre_ok, pre_log, pre_msg = True, [f"Chrome pre-check skipped: {e}"], ""
        if not pre_ok:
            _emit({
                "status": "failure",
                "scenario": scenario_key,
                "message": pre_msg,
                "log": pre_log,
            }, ok=False)
            return
        try:
            if is_multi:
                plan, log, created = _deploy_live_chat_multi(cfg, ctx, owner, profile)
            else:
                plan, log, created = _deploy_live_chat(cfg, ctx, owner, profile)
        except Exception as e:
            _emit({
                "status": "failure",
                "scenario": scenario_key,
                "message": _tr(f"Deployment failed: {e}", f"部署失败：{e}"),
                "log": [*pre_log, _tr(f"Error: {e}", f"错误：{e}")],
            }, ok=False)
            return
        log = [*pre_log, *log]
        _emit({
            "status": "success",
            "scenario": scenario_key,
            "stub": False,
            "plan": plan,
            "created": created,
            "log": ["Config validated.", *log, "Deployment complete."],
            "message": (
                f"{profile.label} deployed: {plan['agents']} agent(s) and {plan['tasks']} task(s) "
                + (f"for {plan.get('stores')} store(s) with a shared Q&A pool. "
                   if is_multi else "referencing the shared skills (no copies). ")
                + (f"{len(plan.get('needs_login') or [])} store(s) need a one-time login."
                   if plan.get("needs_login") else "")
            ),
        }, ok=True)
        return

    if scenario_key in _OPS_PLATFORMS:
        from ..base.context import get_context
        ctx = get_context()
        owner = ctx.username or os.environ.get("ECAN_DEPLOY_OWNER") or "default"
        try:
            plan, log, created = _deploy_operations(cfg, ctx, owner, scenario_key)
        except Exception as e:
            _emit({
                "status": "failure",
                "scenario": scenario_key,
                "message": _tr(f"Deployment failed: {e}", f"部署失败：{e}"),
                "log": [_tr(f"Error: {e}", f"错误：{e}")],
            }, ok=False)
            return
        _emit({
            "status": "success",
            "scenario": scenario_key,
            "stub": False,
            "plan": plan,
            "created": created,
            "log": ["Config validated.", *log, "Deployment complete."],
            "message": (
                _tr(f"Deployed {plan['agents']} agent(s) and {plan['tasks']} task(s).",
                    f"已部署 {plan['agents']} 个智能体和 {plan['tasks']} 个任务。")
                + (_tr(" The store needs a one-time login.", "店铺需要登录一次。")
                   if plan.get("needs_login") else "")
            ),
        }, ok=True)
        return

    try:
        plan, log = recipe(scenario_key, cfg)
    except Exception as e:
        _emit({
            "status": "failure",
            "scenario": scenario_key,
            "message": _tr(f"Recipe failed: {e}", f"生成失败：{e}"),
            "log": [_tr(f"Recipe error: {e}", f"生成出错：{e}")],
        }, ok=False)
        return

    log = ["Config validated.", *log, "STUB: resources not persisted yet (per-scenario generation pending)."]

    _emit({
        "status": "success",
        "scenario": scenario_key,
        "stub": True,
        "plan": plan,
        "log": log,
        "message": (
            f"Planned {plan['agents']} agent(s), {plan['skills']} skill(s), "
            f"{plan['tasks']} task(s) for {scenario_key}."
        ),
    }, ok=True)
