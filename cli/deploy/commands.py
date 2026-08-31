#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fast Deploy Commands — generate the resources (agents, skills, tasks) for a
business scenario from a single config file.

    ecan deploy scenario -c config.json [-o result.json]

The config file is produced by the app's Fast Deploy panel and looks like:

    {
      "scenario": "douyin_cs",
      "config": { "store_urls": ["https://…"], "qa_agents": 6 }
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


def _recipe_operation(scenario: str, cfg: dict):
    urls = cfg.get("store_urls") or []
    n = max(1, len(urls))
    log = [
        f"Scenario: {scenario}",
        f"Store URLs: {len(urls)}",
        f"[plan] {n} operation agent(s) (one per store)",
        f"[plan] 1 skill (store operation)",
        f"[plan] {n} task(s)",
    ]
    plan = {"agents": n, "skills": 1, "tasks": n}
    return plan, log


_RECIPES = {
    "douyin_cs": _recipe_customer_service,
    "tmall_cs": _recipe_customer_service,
    "amazon_ops": _recipe_operation,
    "ebay_ops": _recipe_operation,
    "etsy_ops": _recipe_operation,
    "shopify_ops": _recipe_operation,
    "tiktok_ops": _recipe_operation,
}


# ── Real Douyin/抖店 customer-service deployment (shared-skill model) ────────
# SHARED_SKILL_MULTI_TASK_PLAN: the deployment REFERENCES the two published
# Feige skills (public / rentable / ¥0) instead of cloning per-agent copies:
#
#   skill_4f24592c81894ae7  飞鸽客服问答00  ← N Q&A tasks 飞鸽客服应答00N
#   skill_71209937ed7449bf  飞鸽客服前台00  ← 1 front-desk task 飞鸽客服前台001
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
_DDCS_FD_SKILL_ID = "skill_71209937ed7449bf"   # 飞鸽客服前台00
_DDCS_QA_SKILL_NAME = "飞鸽客服问答00"
_DDCS_FD_SKILL_NAME = "飞鸽客服前台00"
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
        log.append(f"WARNING: run.env write failed ({e}) — set the Feige env flags manually.")


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


def _ensure_sales_org(ctx, owner: str, log: list) -> str:
    """Return the Sales organization id, creating the org if absent."""
    result = ctx.db.org_service.search_orgs(name=_DDCS_SALES_ORG_NAME)
    rows = result.get("data") or [] if isinstance(result, dict) else []
    exact = [r for r in rows
             if str(r.get("name", "")).strip().lower() == _DDCS_SALES_ORG_NAME.lower()]
    if exact:
        org_id = exact[0].get("id")
        log.append(f"Sales organization found: {org_id}")
        return org_id
    created = ctx.db.org_service.add_org({
        "name": _DDCS_SALES_ORG_NAME,
        "description": "Sales organization (created by Fast Deploy)",
        "owner": owner,
    })
    if not created.get("success"):
        raise RuntimeError(f"Could not find or create Sales organization: {created.get('error')}")
    org_id = created.get("id")
    log.append(f"Sales organization created: {org_id}")
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
    from utils.user_path_helper import get_user_data_dir
    from agent.ec_skills.prompt_loader import SAMPLE_PROMPTS_DIR

    log_user = os.environ.get("ECAN_LOG_USER") or None
    user_dir = Path(get_user_data_dir(log_user, subdir="my_prompts"))
    subscribed_dir = Path(get_user_data_dir(log_user, subdir="subscribed_prompts"))
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


def _deploy_douyin_cs(cfg: dict, ctx, owner: str):
    """Create the real Douyin/抖店 CS deployment (shared-skill model).
    Returns (plan, log, created). Raises on hard failure — the caller turns
    that into the failure result the Fast Deploy panel pops."""
    from utils.logger_helper import logger_helper as logger

    store_urls = [u.strip() for u in (cfg.get("store_urls") or []) if u and str(u).strip()]
    qa_n = int(cfg.get("qa_agents") or 6)
    log = []
    created = {"skills": [], "tasks": [], "agents": []}

    # ── 1+2) Visibility checks: the two published skills, then their prompts
    #    (prompt visibility rides the skills' author identity).
    skill_rows = {}
    for sid, sname in ((_DDCS_QA_SKILL_ID, _DDCS_QA_SKILL_NAME),
                       (_DDCS_FD_SKILL_ID, _DDCS_FD_SKILL_NAME)):
        r = ctx.db.skill_service.get_skill_by_id(sid)
        row = r.get("data") if isinstance(r, dict) and r.get("success") else None
        if not row:
            msg = (f"Skill {sname} ({sid}) is not visible — subscribe to it in the "
                   f"skill store (public / rentable / ¥0) and retry.")
            logger.error(f"[FastDeploy][douyin_cs] {msg}")
            raise RuntimeError(msg)
        skill_rows[sid] = row
    log.append(f"Skills verified: {_DDCS_QA_SKILL_NAME} ({_DDCS_QA_SKILL_ID}), "
               f"{_DDCS_FD_SKILL_NAME} ({_DDCS_FD_SKILL_ID})")

    for pid, pname, sid in ((_DDCS_QA_PROMPT_ID, "飞鸽客服应答0", _DDCS_QA_SKILL_ID),
                            (_DDCS_QA_SOCIAL_PROMPT_ID, "飞鸽社交应答0", _DDCS_QA_SKILL_ID),
                            (_DDCS_QA_RAG_PROMPT_ID, "飞鸽RAG路由分类0", _DDCS_QA_SKILL_ID),
                            (_DDCS_FD_PROMPT_ID, "飞鸽客服前台0", _DDCS_FD_SKILL_ID)):
        if not _prompt_visible(pid, _skill_author(skill_rows[sid]), log):
            msg = (f"Prompt {pname} ({pid}) is not visible — it should come with "
                   f"the subscribed skill {skill_rows[sid].get('name')}; re-subscribe "
                   f"or sync prompts and retry.")
            logger.error(f"[FastDeploy][douyin_cs] {msg}")
            raise RuntimeError(msg)
    log.append(f"Prompts verified: 飞鸽客服应答0 ({_DDCS_QA_PROMPT_ID}), "
               f"飞鸽社交应答0 ({_DDCS_QA_SOCIAL_PROMPT_ID}), "
               f"飞鸽RAG路由分类0 ({_DDCS_QA_RAG_PROMPT_ID}), "
               f"飞鸽客服前台0 ({_DDCS_FD_PROMPT_ID})")

    # ── Account API key: make sure the account has one (create when absent).
    #    Same key the web app's Account page manages (myAPIKeygen store).
    #    Best-effort: the douyin_cs runtime doesn't hard-require it yet, so
    #    a failure here logs a warning instead of failing the deployment.
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
        logger.warning(f"[FastDeploy][douyin_cs] API key ensure failed (non-fatal): {_key_err}")
        log.append(f"API key check failed (non-fatal): {_key_err}")

    # ── Store URL propagation: per-task variables. apply_task_vars seeds
    #    these into every run's prompt variables, so the skills' prompts can
    #    reference {{store_url}} / {{store_urls}}.
    task_vars = {"store_url": store_urls[0], "store_urls": ",".join(store_urls)}
    log.append(f"Task variables: store_url={store_urls[0]} (+{len(store_urls) - 1} more)"
               if len(store_urls) > 1 else f"Task variables: store_url={store_urls[0]}")

    # ── Vehicle: pin the new agents to THIS machine (affinity gate).
    # ONLY the verified local machine id may be pinned. Never fall back to an
    # arbitrary DB row: on the v0.9.95t customer machine the first row was a
    # stale vehicle, every agent got pinned to it, and the affinity gate then
    # skipped ALL of them at launch ("assigned to vehicle cccdef54.., local
    # vehicle is 3bee2c61.."). Unpinned agents fail OPEN — they run anywhere.
    vehicle_id = None
    try:
        from agent.ec_agents.vehicle_affinity import resolve_local_vehicle_id
        vehicle_id = resolve_local_vehicle_id(
            username=os.environ.get("ECAN_LOG_USER") or owner) or None
    except Exception as e:
        log.append(f"WARNING: local vehicle id resolution failed ({e}).")
    if not vehicle_id:
        log.append("WARNING: no local vehicle id — agents created UNPINNED (they will run on any host).")

    # ── Sales organization.
    org_id = _ensure_sales_org(ctx, owner, log)

    def _add_task(name: str, skill_id: str, extra_vars: dict | None = None) -> str:
        tvars = dict(task_vars)
        if extra_vars:
            tvars.update(extra_vars)
        tr = ctx.db.task_service.add_task({
            "name": name, "owner": owner, "source": "fast_deploy",
            "description": "抖店客服 — Fast Deploy (shared skill)",
            "task_type": "browser_automation", "trigger": "auto", "status": "pending",
            "settings": {"task_vars": tvars},
        })
        if not tr.get("success"):
            raise RuntimeError(f"add_task({name}) failed: {tr.get('error')}")
        tid = tr.get("id")
        created["tasks"].append(tid)
        link = ctx.db.task_service.add_skill_to_task(tid, skill_id, role="primary")
        if not (isinstance(link, dict) and link.get("success")):
            raise RuntimeError(
                f"link task {name} → skill {skill_id} failed: {(link or {}).get('error')}")
        return tid

    def _add_agent(name: str, skill_id: str, task_id: str) -> str:
        adata = {
            "name": name,
            "description": "抖店客服 — Fast Deploy (shared skill)",
            "skills": [skill_id],
            "org_id": org_id,
        }
        # Task links must not depend on vehicle resolution: without them the
        # agents exist but never run their tasks (deep-trace finding — a CLI
        # subprocess can fail vehicle resolution where the GUI would not).
        if task_id:
            adata["tasks"] = [task_id]
        if vehicle_id:
            adata["vehicle_id"] = vehicle_id
        ar = ctx.db.agent_service.create_agent_from_data(adata, owner)
        if not ar.get("success"):
            raise RuntimeError(f"create agent {name} failed: {ar.get('error')}")
        aid = ar.get("id")
        created["agents"].append(aid)
        return aid

    # ── Feige runtime env flags → <appdata>/run.env (applied on next app start).
    _write_run_env(_DDCS_FEIGE_ENV, log)

    # ── 3A/4A) Front-desk task + agent FIRST: the Q&A tasks must carry the
    #    front-desk agent's id in task_vars, because the shared Q&A skill's
    #    pend_event node filters on {{front_desk_agent_id}} — resolved from
    #    task_vars at task-launch time (runner._extract_event_types_from_skill).
    fd_task_id = _add_task("飞鸽客服前台001", _DDCS_FD_SKILL_ID)
    fd_agent_id = _add_agent("前台小张", _DDCS_FD_SKILL_ID, fd_task_id)
    log.append(f"Created task 飞鸽客服前台001 → {_DDCS_FD_SKILL_NAME}")
    log.append(f"Created front-desk agent 前台小张 ({fd_agent_id}, org=Sales)")

    # ── 3B/4B) Q&A tasks (carrying front_desk_agent_id) + agents.
    qa_task_ids = []
    for i in range(1, qa_n + 1):
        qa_task_ids.append(_add_task(f"飞鸽客服应答{i:03d}", _DDCS_QA_SKILL_ID,
                                     extra_vars={"front_desk_agent_id": fd_agent_id}))
    for name, tid in zip(_draw_qa_names(qa_n), qa_task_ids):
        _add_agent(f"客服小{name}", _DDCS_QA_SKILL_ID, tid)
    log.append(f"Created {qa_n} Q&A task(s) 飞鸽客服应答001..{qa_n:03d} → {_DDCS_QA_SKILL_NAME} "
               f"(task_vars.front_desk_agent_id={fd_agent_id})")
    log.append(f"Created {qa_n} Q&A agent(s) 客服小X (org=Sales)")

    plan = {
        "agents": len(created["agents"]),
        "skills": 0,  # shared skills referenced, none created
        "tasks": len(created["tasks"]),
    }
    logger.info(
        f"[FastDeploy][douyin_cs] SUCCESS: {plan['agents']} agent(s), {plan['tasks']} task(s) "
        f"referencing shared skills {_DDCS_QA_SKILL_ID}/{_DDCS_FD_SKILL_ID}; "
        f"store_url + front_desk_agent_id propagated via task_vars"
    )
    return plan, log, created


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
        _emit({"status": "failure", "message": f"Invalid config file: {e}", "log": []}, ok=False)
        return

    scenario_key = str(payload.get("scenario") or "").strip()
    cfg = payload.get("config") or {}
    recipe = _RECIPES.get(scenario_key)

    if not recipe:
        _emit({
            "status": "failure",
            "scenario": scenario_key,
            "message": f"Unknown scenario: {scenario_key!r}",
            "log": [f"No recipe registered for {scenario_key!r}"],
        }, ok=False)
        return

    urls = cfg.get("store_urls") or []
    if not isinstance(urls, list):
        _emit({
            "status": "failure",
            "scenario": scenario_key,
            "message": "store_urls must be a list of URLs.",
            "log": ["Validation failed: store_urls is not a list"],
        }, ok=False)
        return
    if not urls:
        _emit({
            "status": "failure",
            "scenario": scenario_key,
            "message": "At least one store URL is required.",
            "log": ["Validation failed: store_urls is empty"],
        }, ok=False)
        return

    # Real deployment for Douyin/抖店 CS (persists agents/skills/tasks);
    # the other scenarios are still stubbed plans.
    if scenario_key == "douyin_cs":
        from ..base.context import get_context
        ctx = get_context()
        owner = ctx.username or os.environ.get("ECAN_DEPLOY_OWNER") or "default"
        try:
            plan, log, created = _deploy_douyin_cs(cfg, ctx, owner)
        except Exception as e:
            _emit({
                "status": "failure",
                "scenario": scenario_key,
                "message": f"Deployment failed: {e}",
                "log": [f"Error: {e}"],
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
                f"抖店客服 deployed: {plan['agents']} agent(s) and {plan['tasks']} task(s) "
                f"referencing the shared Feige skills (no copies). "
                f"Store URL propagated via task variables."
            ),
        }, ok=True)
        return

    try:
        plan, log = recipe(scenario_key, cfg)
    except Exception as e:
        _emit({
            "status": "failure",
            "scenario": scenario_key,
            "message": f"Recipe failed: {e}",
            "log": [f"Recipe error: {e}"],
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
