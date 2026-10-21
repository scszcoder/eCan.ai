#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Store Commands - define stores first, then deploy into them.

A store is the local catalog record (agent/db/models/store_model.py): name,
platform, URLs and the browser profile holding its seller login. The same
module the app's Stores page uses (agent/ec_agents/store_catalog.py) does the
work, so validation -- no URL-derived id, no duplicate id, the profile must
exist -- is identical here.

The CLI has no cloud session, so a store created here is defined LOCALLY; the
app defines/claims it in the cloud when its agents start (store placement).
Point the CLI at a user's database with ECAN_CLI_USER.

Deploy agents into a store with:
  ecan deploy scenario --config cfg.json   (config: {"scenario": "douyin_cs",
                                             "config": {"store_id": ..., "store_urls": [...]}})
"""

from types import SimpleNamespace

import click

from ..base.context import get_context
from ..base.output import get_output


def _mainwin():
    """The slice of MainWindow store_catalog needs: the store service, no agents."""
    svc = getattr(get_context().db, "store_service", None)
    if svc is None:
        raise click.ClickException("store catalog unavailable (database has no store table yet)")
    return SimpleNamespace(ec_db_mgr=SimpleNamespace(store_service=svc), agents=[])


def _print_warnings(out, warnings):
    for w in warnings or []:
        out.warning(w)


@click.group()
def stores():
    """Manage stores (define a store, then deploy agents into it)."""


@stores.command('list')
@click.option('--all', 'include_archived', is_flag=True, help='Include archived stores')
@click.option('--format', '-f', 'format', type=click.Choice(['table', 'json', 'simple']), default='table')
def list_stores(include_archived, format):
    """List stores in the local catalog. QUERY command."""
    out = get_output()
    rows = _mainwin().ec_db_mgr.store_service.list_stores(include_archived=include_archived)
    if format == 'json':
        out.json(rows)
        return
    if format == 'simple':
        for r in rows:
            click.echo(r['store_id'])
        return
    out.table('Stores', ['store_id', 'name', 'platform', 'profile', 'urls', 'status', 'source'],
              [[r['store_id'], r['name'], r['platform'], r.get('browser_profile_id') or '-',
                len(r.get('store_urls') or []), r['status'], r['source']] for r in rows])


@stores.command('show')
@click.argument('store_id')
def show_store(store_id):
    """Show one store. QUERY command."""
    out = get_output()
    rec = _mainwin().ec_db_mgr.store_service.get_store(store_id)
    if not rec:
        raise click.ClickException(f"no store {store_id!r}")
    out.json(rec)


@stores.command('create')
@click.option('--id', 'store_id', required=True, help='Permanent store id, e.g. douyin-小店一号')
@click.option('--name', required=True, help='Display name')
@click.option('--platform', required=True, help='douyin, etsy, pinduoduo, ... or any name')
@click.option('--url', 'urls', multiple=True, help='Store URL (repeatable)')
@click.option('--profile', 'profile_id', default='', help='Browser profile holding the seller login')
@click.option('--unassigned', is_flag=True, help='Do not assign to this machine; the first machine to run it claims it')
def create_store(store_id, name, platform, urls, profile_id, unassigned):
    """Define a store. OPERATION command."""
    from agent.ec_agents import store_catalog
    out = get_output()
    try:
        res = store_catalog.create_store(_mainwin(), {
            'store_id': store_id, 'name': name, 'platform': platform, 'store_urls': list(urls),
            'browser_profile_id': profile_id, 'assign': 'none' if unassigned else 'here',
        })
    except ValueError as e:
        raise click.ClickException(str(e))
    _print_warnings(out, res.get('warnings'))
    out.success(f"Store {store_id!r} created")


@stores.command('update')
@click.argument('store_id')
@click.option('--name', default=None)
@click.option('--platform', default=None)
@click.option('--url', 'urls', multiple=True, help='Replace the URL list (repeatable)')
@click.option('--profile', 'profile_id', default=None, help="Browser profile id ('' to clear)")
def update_store(store_id, name, platform, urls, profile_id):
    """Edit a store's definition. OPERATION command."""
    from agent.ec_agents import store_catalog
    out = get_output()
    data = {'store_id': store_id}
    if name is not None:
        data['name'] = name
    if platform is not None:
        data['platform'] = platform
    if urls:
        data['store_urls'] = list(urls)
    if profile_id is not None:
        data['browser_profile_id'] = profile_id
    try:
        store_catalog.update_store(_mainwin(), data)
    except ValueError as e:
        raise click.ClickException(str(e))
    out.success(f"Store {store_id!r} updated")


@stores.command('reconcile')
@click.option('--store', 'store_id', default=None, help='Only this store (default: all)')
@click.option('--format', '-f', 'format', type=click.Choice(['table', 'json']), default='table')
@click.option('--apply', 'apply_fix', is_flag=True,
              help='Enact the plan (retire duplicates, re-point stale Q&A). Default: report only.')
@click.option('--force', is_flag=True, help='Skip the confirmation prompt with --apply')
def reconcile_stores(store_id, format, apply_fix, force):
    """Report (and optionally fix) front-desk wiring per store.

    The target is exactly ONE front desk per store, and every store's Q&A pool
    pointed at that front desk. Two things drift:
      * a legacy deploy (前台小张 / 飞鸽客服前台001) and a newer store-scoped one
        (前台-<店铺名>) both landed — a DUPLICATE front desk;
      * a store's front desk was re-created, but its Q&A pool still pend-waits on
        the OLD front_desk_agent_id — STALE wiring, so that store never replies.

    Read-only by default. With ``--apply`` it enacts the plan through the running
    app (so the cloud copy is cleaned / the running tasks update), else directly
    against the local DB with a cloud sync. Restart eCan afterwards.
    """
    from agent.ec_agents.store_overview import (
        is_front_desk_name, plan_front_desk_reconcile, plan_qa_rewire,
    )
    out = get_output()
    ctx = get_context()
    svc = getattr(ctx.db, "store_service", None)
    if svc is None:
        raise click.ClickException("store catalog unavailable (database has no store table yet)")
    store_names = {r["store_id"]: r.get("name") or r["store_id"]
                   for r in svc.list_stores(include_archived=False)}

    res = ctx.db.agent_service.query_agents_with_relations(
        include_skills=False, include_tasks=True, include_org=False)
    agents = (res or {}).get("data") or []
    front_desks, qa_tasks = [], []
    for a in agents:
        aid, aname = a.get("id") or "", a.get("name") or ""
        for t in a.get("tasks") or []:
            tname = t.get("name") or ""
            tv = ((t.get("metadata") or {}).get("task_vars") or {}) if isinstance(t.get("metadata"), dict) else {}
            sid = str(tv.get("store_id") or "").strip()
            if not sid or (store_id and sid != store_id):
                continue
            if is_front_desk_name(tname):
                front_desks.append({"store_id": sid, "agent_id": aid, "agent_name": aname,
                                     "task_id": t.get("id") or "", "task_name": tname})
            elif str(tv.get("front_desk_agent_id") or "").strip():
                qa_tasks.append({"store_id": sid, "task_id": t.get("id") or "",
                                 "task_name": tname,
                                 "front_desk_agent_id": str(tv.get("front_desk_agent_id")).strip()})

    plans = plan_front_desk_reconcile(front_desks, store_names)
    rewires = plan_qa_rewire(front_desks, qa_tasks, store_names)

    if format == 'json':
        out.json({"duplicate_front_desks": plans, "stale_qa_wiring": rewires})
        if apply_fix:
            _reconcile_apply(ctx, out, plans, rewires, force)
        return

    if not plans and not rewires:
        out.success("Front-desk wiring is consistent (one front desk per store, Q&A pointed at it).")
        return
    if plans:
        rows = []
        for p in plans:
            keep = p["keep"]
            rows.append([
                p["store_id"], p["store_name"] or '-',
                (keep.get("agent_name") if keep else '— pick —'),
                ", ".join(sorted({r.get("agent_name") or "" for r in p["retire"]})) or '-',
                p["note"],
            ])
        out.table('Duplicate front desks', ['store', 'name', 'keep', 'retire', 'note'], rows)
    if rewires:
        out.table('Stale Q&A wiring', ['store', 'task', 'from', 'to'],
                  [[r["store_id"], r["task_name"], r["from"], f'{r["to"]} ({r["to_name"]})']
                   for r in rewires])

    if not apply_fix:
        out.warning("Report only. Re-run with --apply to retire duplicates and re-point stale Q&A "
                    "(ambiguous stores are skipped — fix those by hand). Restart eCan afterwards.")
        return
    _reconcile_apply(ctx, out, plans, rewires, force)


def _reconcile_apply(ctx, out, plans, rewires, force):
    """Enact the reconcile plan: retire duplicate front desks and re-point stale
    Q&A wiring. Through the running app when it's up (cloud cleaned, running
    tasks updated), else direct DB + cloud sync. Ambiguous duplicates skipped."""
    retire_agents = [(r.get("agent_id"), r.get("agent_name"), r.get("task_id"), r.get("task_name"))
                     for p in plans if not p.get("ambiguous") for r in p.get("retire") or []]
    if not retire_agents and not rewires:
        out.warning("Nothing to apply (only ambiguous stores, which need a human).")
        return
    n = len(retire_agents) + len(rewires)
    if not force and not out.confirm(
            f"Apply {len(retire_agents)} retire(s) and {len(rewires)} re-point(s)? ({n} change(s))"):
        return

    from ..base.app_client import call_or_exit, edits_via_app
    from ..base.sync import cloud_sync
    from agent.cloud_api.constants import DataType, Operation
    via_app = edits_via_app(ctx.username)

    for agent_id, agent_name, task_id, task_name in retire_agents:
        if via_app:
            if task_id:
                call_or_exit(out, 'delete_agent_task', {'username': ctx.username, 'task_id': task_id}, timeout=120)
            call_or_exit(out, 'delete_agent', {'username': ctx.username, 'agent_id': agent_id}, timeout=120)
        else:
            if task_id:
                ctx.db.task_service.delete_task(task_id)
                cloud_sync(DataType.TASK, {'id': task_id}, Operation.DELETE)
            ctx.db.agent_service.delete_agent(agent_id)
            cloud_sync(DataType.AGENT, {'id': agent_id}, Operation.DELETE)
        out.success(f"Retired duplicate front desk {agent_name!r}")

    for r in rewires:
        tid = r["task_id"]
        settings = _reconcile_task_settings(ctx, tid)
        tv = dict(settings.get("task_vars") or {})
        tv["front_desk_agent_id"] = r["to"]
        settings["task_vars"] = tv
        if via_app:
            rec = {"id": tid, "name": r["task_name"], "metadata": settings}
            call_or_exit(out, 'save_agent_task', {'username': ctx.username, 'task_info': rec}, timeout=120)
        else:
            result = ctx.db.task_service.update_task(tid, {"settings": settings})
            if not (isinstance(result, dict) and result.get("success")):
                out.error(f"Failed to re-point {r['task_name']}: {(result or {}).get('error')}")
                continue
            cloud_sync(DataType.TASK, result.get("data") or {"id": tid, "settings": settings}, Operation.UPDATE)
        out.success(f"Re-pointed Q&A {r['task_name']!r} → {r['to_name']}")

    out.warning("Done. Restart eCan so the fixed wiring takes effect, then re-run "
                "`ecan stores reconcile` to confirm it's clean.")


def _reconcile_task_settings(ctx, task_id):
    """A task's current settings dict (so a re-point merges, not wipes)."""
    try:
        r = ctx.db.task_service.query_tasks(id=task_id)
        row = ((r or {}).get("data") or [{}])[0] if isinstance(r, dict) else {}
        md = row.get("metadata") if isinstance(row.get("metadata"), dict) else row.get("settings")
        return dict(md) if isinstance(md, dict) else {}
    except Exception:
        return {}


@stores.command('archive')
@click.argument('store_id')
@click.option('--restore', is_flag=True, help='Bring an archived store back')
def archive_store(store_id, restore):
    """Archive (or restore) a store locally. OPERATION command."""
    out = get_output()
    if not _mainwin().ec_db_mgr.store_service.set_status(store_id, 'active' if restore else 'archived'):
        raise click.ClickException(f"no store {store_id!r}")
    out.success(f"Store {store_id!r} {'restored' if restore else 'archived'}")
