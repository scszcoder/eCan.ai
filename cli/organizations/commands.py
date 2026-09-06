#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Organization Management Commands - CRUD over the local org tree.

Operates on the SAME per-user DB the app reads (via ``ctx.db.org_service``);
writes propagate to the cloud through the offline sync queue, exactly like
``ecan skills`` / ``ecan agents``. The org service already backs Fast Deploy's
Sales-org bootstrap — this exposes it directly.
"""

import json as _json

import click

from ..base.context import get_context
from ..base.output import get_output
from ..base.config import get_config
from ..base.decorators import requires_auth


def _resolve_org(ctx, out, identifier):
    """Return an org id from an id or an exact/searched name."""
    svc = ctx.db.org_service
    # id fast-path
    res = svc.get_org_by_id(identifier)
    if isinstance(res, dict) and res.get('success') and res.get('data'):
        return identifier
    # name lookup
    found = svc.search_orgs(name=identifier)
    rows = (found.get('data') or []) if isinstance(found, dict) else []
    exact = [r for r in rows if str(r.get('name', '')).strip().lower() == identifier.strip().lower()]
    picked = exact or rows
    if len(picked) == 1:
        return picked[0].get('id')
    if not picked:
        out.error(f"Organization not found: {identifier}")
        raise SystemExit(1)
    out.error(f"Ambiguous name '{identifier}' — matches {len(picked)}; use the id")
    raise SystemExit(1)


@click.group()
def org():
    """Manage organizations (the agent org tree)."""


@org.command('list')
@click.option('--name', '-n', help='Filter by name (substring)')
@click.option('--limit', '-l', default=50, help='Max rows (default 50)')
@click.option('--format', '-f', 'format', type=click.Choice(['table', 'json', 'simple']), default='table')
def list_orgs(name, limit, format):
    """List organizations. QUERY command."""
    ctx = get_context()
    out = get_output()
    if limit < 1:
        out.error("--limit must be >= 1")
        raise SystemExit(1)
    limit = min(limit, get_config().get('max_limit', 1000))
    try:
        result = ctx.db.org_service.search_orgs(name=name) if name else ctx.db.org_service.get_all_orgs()
        rows_data = (result.get('data') or []) if isinstance(result, dict) else []
        rows_data = rows_data[:limit]
        if format == 'json':
            out.json({'organizations': rows_data, 'count': len(rows_data)})
        elif format == 'simple':
            for o in rows_data:
                out.print(f"{o.get('id', '')}\t{o.get('name', '')}\t{o.get('status', '')}")
        else:
            rows = [[
                (o.get('id') or '')[:12] + ('...' if len(o.get('id') or '') > 12 else ''),
                o.get('name', ''), o.get('parent_id', '') or '-', o.get('status', ''),
            ] for o in rows_data]
            out.table("Organizations", ["ID", "Name", "Parent", "Status"], rows)
    except Exception as e:
        out.error(f"Failed to list organizations: {e}")
        raise SystemExit(1)


@org.command()
@click.argument('identifier')
@click.option('--format', '-f', 'format', type=click.Choice(['table', 'json']), default='table')
def get(identifier, format):
    """Show one organization by id or name. QUERY command."""
    ctx = get_context()
    out = get_output()
    org_id = _resolve_org(ctx, out, identifier)
    try:
        result = ctx.db.org_service.get_org_by_id(org_id)
    except Exception as e:
        out.error(f"Failed to get organization: {e}")
        raise SystemExit(1)
    data = result.get('data') if isinstance(result, dict) else None
    if not data:
        out.error(f"Organization not found: {identifier}")
        raise SystemExit(1)
    if format == 'json':
        out.json(data)
    else:
        out.title(f"Organization: {data.get('name', '')}")
        for k in ('id', 'name', 'description', 'parent_id', 'org_type', 'owner', 'status'):
            if data.get(k) not in (None, ''):
                out.print(f"{k}: {data.get(k)}")


@org.command()
@requires_auth
@click.option('--name', '-n', required=True, help='Organization name (required)')
@click.option('--description', '-d', default='', help='Description')
@click.option('--parent', '-p', 'parent', help='Parent organization id or name')
@click.option('--type', '-t', 'org_type', help='Organization type')
def add(name, description, parent, org_type):
    """Create an organization. OPERATION command (requires auth)."""
    ctx = get_context()
    out = get_output()
    parent_id = _resolve_org(ctx, out, parent) if parent else None
    data = {
        'name': name,
        'description': description,
        'owner': ctx.username,
        'status': 'active',
    }
    if parent_id:
        data['parent_id'] = parent_id
    if org_type:
        data['org_type'] = org_type
    try:
        result = ctx.db.org_service.add_org(data)
    except Exception as e:
        out.error(f"Failed to create organization: {e}")
        raise SystemExit(1)
    if not result.get('success'):
        out.error(f"Failed: {result.get('error')}")
        raise SystemExit(1)
    out.success(f"Organization created (id {result.get('id')})!")
    _sync(result.get('data') or {**data, 'id': result.get('id')}, 'ADD')


@org.command()
@requires_auth
@click.argument('identifier')
@click.option('--name', '-n', help='New name')
@click.option('--description', '-d', help='New description')
@click.option('--parent', '-p', 'parent', help='New parent org id or name')
@click.option('--status', '-s', help='New status (e.g. active, inactive)')
def update(identifier, name, description, parent, status):
    """Update an organization. OPERATION command (requires auth)."""
    ctx = get_context()
    out = get_output()
    org_id = _resolve_org(ctx, out, identifier)
    fields = {}
    if name:
        fields['name'] = name
    if description is not None and description != '':
        fields['description'] = description
    if parent:
        fields['parent_id'] = _resolve_org(ctx, out, parent)
    if status:
        fields['status'] = status
    if not fields:
        out.warning("No fields to update")
        return
    try:
        result = ctx.db.org_service.update_org(org_id, fields)
    except Exception as e:
        out.error(f"Failed to update organization: {e}")
        raise SystemExit(1)
    if not result.get('success'):
        out.error(f"Failed: {result.get('error')}")
        raise SystemExit(1)
    out.success("Organization updated!")
    _sync(result.get('data') or {'id': org_id, **fields}, 'UPDATE')


@org.command()
@requires_auth
@click.argument('identifier')
@click.option('--force', '-f', is_flag=True, help='Skip confirmation')
def remove(identifier, force):
    """Delete an organization. OPERATION command (requires auth)."""
    ctx = get_context()
    out = get_output()
    org_id = _resolve_org(ctx, out, identifier)
    if not force and not out.confirm(f"Delete organization {org_id}?"):
        return
    try:
        result = ctx.db.org_service.delete_org(org_id)
    except Exception as e:
        out.error(f"Failed to delete organization: {e}")
        raise SystemExit(1)
    if not result.get('success'):
        out.error(f"Failed: {result.get('error')}")
        raise SystemExit(1)
    out.success("Organization deleted!")
    _sync({'id': org_id}, 'DELETE')


@org.command()
@click.option('--root', '-r', help='Root org id (default: full forest)')
def tree(root):
    """Print the organization tree. QUERY command."""
    ctx = get_context()
    out = get_output()
    try:
        result = ctx.db.org_service.get_org_tree(root_id=root)
    except Exception as e:
        out.error(f"Failed to get org tree: {e}")
        raise SystemExit(1)
    out.print(_json.dumps(result.get('data') if isinstance(result, dict) else result,
                          ensure_ascii=False, indent=2))


def _sync(data, op_name):
    """Best-effort cloud sync mirroring skills/agents."""
    try:
        from ..base.sync import cloud_sync
        from agent.cloud_api.constants import DataType, Operation
        cloud_sync(DataType.ORGANIZATION, data, getattr(Operation, op_name))
    except Exception:
        pass
