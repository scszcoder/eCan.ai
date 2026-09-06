#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Avatar Management Commands - list/get/add/remove avatars.

Wraps ``agent.avatar.avatar_manager.AvatarManager`` (the same manager the GUI's
avatar IPC handlers use), constructed with the per-user ``avatar_service`` from
``ctx.db``. Upload and delete already handle local files, the DB row, and cloud
(S3 + offline sync) inside the manager, so these commands do not call the
CLI cloud-sync helper.

CRUD note: avatars have no free-text metadata to "update" — the manager exposes
upload (add), delete (remove), and list/get (read); to change an agent's avatar,
use ``ecan agents update``.
"""

import asyncio
import os
from pathlib import Path

import click

from ..base.context import get_context
from ..base.output import get_output
from ..base.config import get_config
from ..base.decorators import requires_auth

_VIDEO_EXT = {'.mp4', '.mov', '.webm', '.m4v'}


def _manager(ctx):
    from agent.avatar.avatar_manager import AvatarManager
    return AvatarManager(user_id=ctx.username or 'default_user',
                         db_service=getattr(ctx.db, 'avatar_service', None))


@click.group()
def avatar():
    """Manage avatars (system + uploaded)."""


@avatar.command('list')
@click.option('--kind', '-k', type=click.Choice(['all', 'system', 'uploaded']), default='all')
@click.option('--limit', '-l', default=100, help='Max rows (default 100)')
@click.option('--format', '-f', 'format', type=click.Choice(['table', 'json', 'simple']), default='table')
def list_avatars(kind, limit, format):
    """List avatars. QUERY command."""
    ctx = get_context()
    out = get_output()
    limit = min(max(1, limit), get_config().get('max_limit', 1000))
    try:
        mgr = _manager(ctx)
        rows = []
        if kind in ('all', 'system'):
            for a in (mgr.get_system_avatars() or []):
                rows.append({'id': a.get('id', ''), 'name': a.get('name', a.get('filename', '')), 'kind': 'system'})
        if kind in ('all', 'uploaded'):
            uploaded = asyncio.run(mgr.get_uploaded_avatars()) if asyncio.iscoroutinefunction(mgr.get_uploaded_avatars) else mgr.get_uploaded_avatars()
            for a in (uploaded or []):
                rows.append({'id': a.get('id', ''), 'name': a.get('name', a.get('filename', '')), 'kind': 'uploaded'})
    except Exception as e:
        out.error(f"Failed to list avatars: {e}")
        raise SystemExit(1)
    rows = rows[:limit]
    if format == 'json':
        out.json({'avatars': rows, 'count': len(rows)})
    elif format == 'simple':
        for a in rows:
            out.print(f"{a['id']}\t{a['name']}\t{a['kind']}")
    else:
        out.table("Avatars", ["ID", "Name", "Kind"],
                  [[a['id'], a['name'], a['kind']] for a in rows])


@avatar.command()
@click.argument('avatar_id')
def get(avatar_id):
    """Show one avatar's info. QUERY command."""
    ctx = get_context()
    out = get_output()
    try:
        info = _manager(ctx).get_avatar_info(avatar_id)
    except Exception as e:
        out.error(f"Failed to get avatar: {e}")
        raise SystemExit(1)
    if not info:
        out.error(f"Avatar not found: {avatar_id}")
        raise SystemExit(1)
    out.json(info)


@avatar.command()
@requires_auth
@click.argument('file_path', type=click.Path(exists=True, dir_okay=False))
def add(file_path):
    """Upload an image (or video) as a new avatar. OPERATION command (requires auth)."""
    ctx = get_context()
    out = get_output()
    p = Path(file_path)
    data = p.read_bytes()
    is_video = p.suffix.lower() in _VIDEO_EXT
    try:
        mgr = _manager(ctx)
        coro = mgr.upload_avatar_video(data, p.name) if is_video else mgr.upload_avatar(data, p.name)
        result = asyncio.run(coro)
    except Exception as e:
        out.error(f"Failed to upload avatar: {e}")
        raise SystemExit(1)
    if not result.get('success'):
        out.error(f"Failed: {result.get('error')}")
        raise SystemExit(1)
    out.success(f"Avatar uploaded (id {result.get('id')})!")


@avatar.command()
@requires_auth
@click.argument('avatar_id')
@click.option('--force', '-f', is_flag=True, help='Skip confirmation')
def remove(avatar_id, force):
    """Delete an uploaded avatar (local + S3 + DB). OPERATION command (requires auth)."""
    ctx = get_context()
    out = get_output()
    if not avatar_id.startswith('avatar_'):
        out.error("Only uploaded avatars (id 'avatar_<hash>') can be removed; system avatars are read-only.")
        raise SystemExit(1)
    if not force and not out.confirm(f"Delete uploaded avatar {avatar_id}?"):
        return
    try:
        result = asyncio.run(_manager(ctx).delete_uploaded_avatar(avatar_id))
    except Exception as e:
        out.error(f"Failed to delete avatar: {e}")
        raise SystemExit(1)
    if not result.get('success'):
        out.error(f"Failed: {result.get('error')}")
        raise SystemExit(1)
    out.success("Avatar deleted!")
