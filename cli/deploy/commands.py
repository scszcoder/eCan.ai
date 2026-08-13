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

STATUS: the per-scenario generation is STUBBED for now — the command
validates the config, computes the resource PLAN it *would* create, logs
each step, and reports success. Real creation plugs into each recipe
below (it can call the existing `agents/skills/tasks add` service layer
once the scenario recipes are finalized).
"""

import json
import os
import shutil
import uuid
from pathlib import Path
from urllib.parse import urlsplit

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


# ── Real Douyin/抖店 customer-service deployment ─────────────────────────────
# Instantiates the proven Feige templates as real DB records: a front-desk
# skill+agent+task and N Q&A skill-sharing agents, each carrying a task whose
# name contains 客户应答 (how the runtime front-desk auto-discovers Q&A agents).
# Store URLs are baked into the front-desk browser-automation monitor's
# page_url_patterns. See docs mapping in the Fast Deploy design notes.

# Prompt ids the Feige skills reference (must exist in my_prompts/ at runtime).
_FEIGE_PROMPT_IDS = ("pr-198938", "pr-278012", "pr-101789", "pr-701210")
# Feige IM host the front-desk always monitors (in addition to store hosts).
_FEIGE_IM_HOST = "im.jinritemai.com"


def _host_of(url: str) -> str:
    try:
        return urlsplit(url).hostname or url
    except Exception:
        return url


def _inject_store_urls(workflow: dict, store_urls: list) -> None:
    """Set every browser-automation monitor's `page_url_patterns` (a JSON
    string inside `cdpFilterExpr`) to the Feige IM host + the store hosts.
    Walks the workflow so it's robust to node/block nesting changes."""
    patterns, seen = [], set()
    for h in [_FEIGE_IM_HOST, *(_host_of(u) for u in store_urls)]:
        if h and h not in seen:
            seen.add(h)
            patterns.append(h)

    def walk(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k == "cdpFilterExpr" and isinstance(v, str) and "page_url_patterns" in v:
                    try:
                        parsed = json.loads(v)
                        parsed["page_url_patterns"] = patterns
                        obj[k] = json.dumps(parsed, ensure_ascii=False)
                    except Exception:
                        pass
                else:
                    walk(v)
        elif isinstance(obj, list):
            for it in obj:
                walk(it)

    walk(workflow)


def _copy_feige_prompts(project_root: Path):
    """Copy the canonical Feige prompt templates into the per-user my_prompts
    dir (preserving their ids) so the skills' prompt refs resolve at runtime."""
    dest = None
    try:
        from cli.prompts.commands import _my_prompts_dir
        try:
            dest = Path(_my_prompts_dir())
        except TypeError:
            from ..base.context import get_context
            dest = Path(_my_prompts_dir(get_context()))
    except Exception:
        dest = project_root / "my_prompts"
    dest.mkdir(parents=True, exist_ok=True)

    copied = []
    for pid in _FEIGE_PROMPT_IDS:
        src = project_root / "customer_logs" / f"prompt_{pid}.json"
        if src.exists():
            try:
                shutil.copyfile(src, dest / f"{pid}.json")
                copied.append(pid)
            except Exception:
                pass
    return copied, dest


def _first_vehicle_id(ctx):
    """Best-effort local vehicle id (needed for agent↔task execution links)."""
    try:
        svc = ctx.db.vehicle_service
    except Exception:
        return None
    for method in ("query_vehicles", "get_all_vehicles", "list_vehicles", "get_vehicles"):
        fn = getattr(svc, method, None)
        if not callable(fn):
            continue
        try:
            res = fn()
        except Exception:
            continue
        data = res.get("data") if isinstance(res, dict) else res
        if data:
            first = data[0]
            return first.get("id") if isinstance(first, dict) else getattr(first, "id", None)
    return None


def _deploy_douyin_cs(cfg: dict, ctx, owner: str):
    """Create the real Douyin/抖店 CS deployment. Returns (plan, log, created).
    Raises on hard failure (missing templates / DB write failure)."""
    store_urls = [u.strip() for u in (cfg.get("store_urls") or []) if u and str(u).strip()]
    qa = int(cfg.get("qa_agents") or 6)
    log = []
    created = {"prompts": [], "skills": [], "tasks": [], "agents": []}
    project_root = Path(ctx.project_root)

    # 1) Ensure the prompt files the skills reference exist.
    copied, pdir = _copy_feige_prompts(project_root)
    created["prompts"] = copied
    log.append(f"Prompts ensured in {pdir}: {', '.join(copied) or '(none found)'}")

    # 2) Load the canonical skill templates.
    fd_path = project_root / "customer_logs" / "飞鸽前台0_skill" / "diagram_dir" / "飞鸽前台0_skill.json"
    qa_path = project_root / "customer_logs" / "飞鸽客户应答_skill" / "diagram_dir" / "飞鸽客户应答_skill.json"
    if not fd_path.exists() or not qa_path.exists():
        raise RuntimeError(
            f"Feige skill templates not found under customer_logs/ "
            f"(front-desk present={fd_path.exists()}, Q&A present={qa_path.exists()})"
        )
    fd_tpl = json.loads(fd_path.read_text(encoding="utf-8"))
    qa_tpl = json.loads(qa_path.read_text(encoding="utf-8"))

    # 3) Bake the store URLs into the front-desk monitor.
    _inject_store_urls(fd_tpl.get("workFlow") or {}, store_urls)
    log.append(f"Front-desk page_url_patterns = {_FEIGE_IM_HOST} + {len(store_urls)} store host(s).")

    dep = uuid.uuid4().hex[:8]

    def _add_skill(sid, name, tpl, extra_config=None):
        r = ctx.db.skill_service.add_skill({
            "id": sid,
            "name": name,
            "owner": owner,
            "version": "1.0.0",
            "description": f"Douyin/抖店 CS ({dep}) — fast deploy.",
            "diagram": tpl.get("workFlow"),
            "config": {**(tpl.get("config") or {}), **(extra_config or {})},
            "source": "fast_deploy",
        })
        if not r.get("success"):
            raise RuntimeError(f"add_skill({name}) failed: {r.get('error')}")
        got = r.get("id") or sid
        created["skills"].append(got)
        log.append(f"Created skill {got} ({name})")
        return got

    qa_skill_id = _add_skill(f"skill_ddqa_{dep}", f"抖店客户应答-{dep}", qa_tpl)
    fd_skill_id = _add_skill(f"skill_ddfd_{dep}", f"抖店前台-{dep}", fd_tpl,
                             extra_config={"store_urls": store_urls})

    vehicle_id = _first_vehicle_id(ctx)
    if not vehicle_id:
        log.append("WARNING: no vehicle found — agent↔task links skipped; "
                   "assign a vehicle so the front-desk can auto-discover Q&A agents.")

    def _add_task(name, skill_id, trigger):
        tr = ctx.db.task_service.add_task({
            "name": name, "owner": owner, "source": "fast_deploy",
            "task_type": "browser_automation", "trigger": trigger, "status": "pending",
        })
        if not tr.get("success"):
            raise RuntimeError(f"add_task({name}) failed: {tr.get('error')}")
        tid = tr.get("id")
        created["tasks"].append(tid)
        try:
            ctx.db.task_service.add_skill_to_task(tid, skill_id, role="primary")
        except Exception as e:
            log.append(f"WARNING: link task {tid}→skill {skill_id} failed: {e}")
        return tid

    def _add_agent(name, skill_id, task_id):
        adata = {"name": name, "description": f"Douyin/抖店 CS ({dep})", "skills": [skill_id]}
        if vehicle_id and task_id:
            adata["tasks"] = [task_id]
            adata["vehicle_id"] = vehicle_id
        ar = ctx.db.agent_service.create_agent_from_data(adata, owner)
        if not ar.get("success"):
            raise RuntimeError(f"create agent {name} failed: {ar.get('error')}")
        aid = ar.get("id")
        created["agents"].append(aid)
        return aid

    # 4) Front-desk task + agent.
    fd_task_id = _add_task(f"抖店前台-{dep}", fd_skill_id, "auto")
    _add_agent(f"抖店前台Agent-{dep}", fd_skill_id, fd_task_id)
    log.append("Created front-desk agent + task.")

    # 5) N Q&A agents — each carries a 客户应答 task linked to the shared Q&A skill.
    for i in range(qa):
        qa_task_id = _add_task(f"客户应答-{dep}-{i + 1}", qa_skill_id, "message")
        _add_agent(f"抖店应答Agent-{dep}-{i + 1}", qa_skill_id, qa_task_id)
    log.append(f"Created {qa} Q&A agent(s), each with a 客户应答 task → Q&A skill.")

    plan = {
        "agents": len(created["agents"]),
        "skills": len(created["skills"]),
        "tasks": len(created["tasks"]),
    }
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
                f"Deployed {plan['agents']} agent(s), {plan['skills']} skill(s), "
                f"{plan['tasks']} task(s) for {scenario_key}."
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
