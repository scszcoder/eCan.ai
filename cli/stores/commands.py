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


@stores.command('archive')
@click.argument('store_id')
@click.option('--restore', is_flag=True, help='Bring an archived store back')
def archive_store(store_id, restore):
    """Archive (or restore) a store locally. OPERATION command."""
    out = get_output()
    if not _mainwin().ec_db_mgr.store_service.set_status(store_id, 'active' if restore else 'archived'):
        raise click.ClickException(f"no store {store_id!r}")
    out.success(f"Store {store_id!r} {'restored' if restore else 'archived'}")
