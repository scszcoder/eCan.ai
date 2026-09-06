#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Prompt Management Commands - Manage reusable prompts and templates.

These operate on the REAL prompt store the app loads from: ``my_prompts/*.json``
(user data dir), keyed by ``pr-<id>`` with the friendly name in the ``title``
field. This is the same store the desktop app reads via
``agent.ec_skills.prompt_loader.load_prompt_by_id`` — so a prompt edited here is
picked up by running agents.

Writes go to the local file store first, then push to the cloud through the
offline sync queue (``cloud_sync`` -> ``DataType.PROMPT``), the same path
``ecan skills`` uses — so ``add``/``update``/``copy``/``remove`` propagate to the
cloud, not just the local files. Sync is best-effort: if the machine is offline
or unauthenticated the local write still succeeds and the queue retries.
"""

import os
import re
import json
from uuid import uuid4
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import click

from ..base.output import get_output
from ..base.decorators import requires_auth


# ---------------------------------------------------------------------------
# my_prompts store helpers (mirror gui/ipc/w2p_handlers/prompt_handler.py)
# ---------------------------------------------------------------------------

# File schema keys we persist (matches the app's _serialize_prompt_for_storage
# in gui/ipc/w2p_handlers/prompt_handler.py — keep the two in sync, or an
# --overwrite here silently drops fields the app wrote, e.g. agentChatHistory).
_STORE_KEYS = (
    "id", "title", "topic", "usageCount", "humanInputs",
    "sections", "userSections", "format", "mdContent", "lastModified",
    "rawContent", "agentChatHistory",
)


def _my_prompts_dir() -> Path:
    """The user-specific my_prompts directory the app loads from.

    Must resolve the SAME per-user dir as the running app (keyed by
    MainWindow.log_user): email logins map 'a@b.com' → 'a_b_com'; non-email
    usernames (e.g. CN WeChat 'wechat_<openid>') get the app's synthetic
    '@local' domain → '<name>_local'. Resolution order:
      1. ECAN_LOG_USER — the exact dir name, set by app-spawned subprocesses
      2. the CLI session/ECAN_CLI_USER username, mapped like the app does
      3. app_context fallback (in-process use) — note: with no user at all
         this lands in 'default_user/', a store the app never reads.
    """
    from utils.user_path_helper import get_user_data_dir
    log_user = os.environ.get("ECAN_LOG_USER")
    if log_user:
        return Path(get_user_data_dir(user_email=log_user, subdir="my_prompts"))
    username = None
    try:
        from ..base.context import get_context
        username = get_context().username
    except Exception:
        pass
    if username:
        if "@" not in username:
            # Mirror MainGUI's synthetic domain for non-email logins so the
            # dir comes out '<name>_local', matching the running app.
            username = f"{username}@local"
        return Path(get_user_data_dir(user_email=username, subdir="my_prompts"))
    return Path(get_user_data_dir(subdir="my_prompts"))


def _slugify(value: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(value or "").strip())
    return re.sub(r"_+", "_", s).strip("_").lower() or "prompt"


def _load_prompt_docs() -> List[Dict[str, Any]]:
    """Load every prompt JSON in my_prompts. Each doc carries a private
    ``__path`` so callers can rewrite/delete the source file."""
    docs: List[Dict[str, Any]] = []
    directory = _my_prompts_dir()
    if not directory.exists():
        return docs
    for file_path in directory.glob("*.json"):
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(data, dict) and data.get("id"):
            data["__path"] = str(file_path)
            docs.append(data)
    return docs


def _find_by_title(name: str) -> Optional[Dict[str, Any]]:
    """Resolve a friendly name to a prompt doc by ``title`` (exact then partial,
    case-insensitive). This is the name->id resolution the proposals rely on."""
    target = str(name or "").strip().lower()
    if not target:
        return None
    docs = _load_prompt_docs()
    for d in docs:
        if str(d.get("title") or "").strip().lower() == target:
            return d
    for d in docs:
        if target in str(d.get("title") or "").strip().lower():
            return d
    return None


def _write_doc(doc: Dict[str, Any], old_path: Optional[str] = None) -> Path:
    """Persist a prompt doc to my_prompts as ``{slug(title)}_{slug(id)}.json``
    (the app's filename convention). Removes the previous file if the name
    changed so we don't leave a stale duplicate."""
    directory = _my_prompts_dir()
    directory.mkdir(parents=True, exist_ok=True)
    title = doc.get("title") or doc.get("id")
    filename = f"{_slugify(title)}_{_slugify(doc['id'])}.json"
    path = directory / filename
    if old_path and Path(old_path).resolve() != path.resolve():
        try:
            Path(old_path).unlink()
        except Exception:
            pass
    payload = {k: v for k, v in doc.items() if k in _STORE_KEYS}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _construct_content(doc: Dict[str, Any]) -> str:
    """Render a prompt doc to its final text (mdContent wins, else sections)."""
    from agent.ec_skills.prompt_loader import construct_prompt_from_data
    return construct_prompt_from_data({k: v for k, v in doc.items() if k != "__path"})


@click.group()
def prompts():
    """
    Prompt management commands.

    OPERATION commands for creating, editing, and deleting prompts.
    QUERY commands for listing and retrieving prompts.

    Prompts are stored as JSON in the app's my_prompts library and are loaded
    by running agents. Edits here are local; the app syncs them to cloud.

    Examples:
      ecan prompts list
      ecan prompts get travel_agent0
      ecan prompts add -n greeting -c "Hello!"
    """
    pass


@prompts.command('list')
@click.option('--name', '-n',
              help='Filter prompts by name (case-insensitive partial match)')
@click.option('--format', '-f', type=click.Choice(['table', 'json', 'simple']),
              default='table',
              help='Output format (default: table)')
def list_prompts(name, format):
    """
    List all prompts.

    QUERY command - lists prompts from the my_prompts library.

    Examples:
      ecan prompts list
      ecan prompts list --name "travel"
      ecan prompts list --format json
    """
    out = get_output()

    needle = (name or "").strip().lower()
    rows_data = []
    for d in _load_prompt_docs():
        title = str(d.get("title") or d.get("id"))
        if needle and needle not in title.lower():
            continue
        rows_data.append({'name': title, 'id': d.get('id', ''), 'path': d.get('__path', '')})

    rows_data.sort(key=lambda r: r['name'].lower())

    if not rows_data:
        out.warning("No prompts found")
        out.info("Use 'ecan prompts add' to create one")
        return

    if format == 'json':
        out.json({'prompts': rows_data, 'count': len(rows_data)})
    elif format == 'simple':
        for p in rows_data:
            out.print(p['name'])
    else:
        rows = [[p['name'], p['id']] for p in rows_data]
        out.table("Prompts", ["Name", "ID"], rows)


@prompts.command()
@click.argument('name')
def get(name):
    """
    Get prompt content.

    QUERY command - displays the rendered content of a prompt.

    Examples:
      ecan prompts get travel_agent0
    """
    out = get_output()

    doc = _find_by_title(name)
    if not doc:
        out.error(f"Prompt not found: {name}")
        out.print("Run 'ecan prompts list' to see available prompts")
        raise SystemExit(1)

    out.title(f"Prompt: {doc.get('title')} (id {doc.get('id')})")
    out.print(_construct_content(doc))


@prompts.command()
@requires_auth
@click.option('--name', '-n', required=True,
              help='Prompt name (required)')
@click.option('--content', '-c',
              help='Prompt content (use \\n for newlines)')
@click.option('--file', '-f', 'file_path', type=click.Path(exists=True),
              help='Read content from file')
@click.option('--overwrite', is_flag=True,
              help='Replace the prompt if it already exists')
def add(name, content, file_path, overwrite):
    """
    Create (or overwrite) a prompt.

    OPERATION command - writes a prompt into the my_prompts library. With
    --overwrite, an existing prompt of the same name keeps its id and only its
    content changes (so agents that reference it stay wired up).

    Examples:
      ecan prompts add -n greeting -c "Hello, welcome!"
      ecan prompts add -n travel_agent0 -f ./new.txt --overwrite
    """
    out = get_output()

    if file_path:
        content = Path(file_path).read_text(encoding="utf-8")
    if not content:
        out.error("Provide content via --content or --file")
        raise SystemExit(1)

    existing = _find_by_title(name)
    if existing and not overwrite:
        out.error(f"Prompt already exists: {name}")
        out.info("Use --overwrite to replace it")
        raise SystemExit(1)

    if existing:
        doc = {k: v for k, v in existing.items() if k != "__path"}
        prompt_id = doc.get("id")
        doc["mdContent"] = content
        doc["format"] = "md"
        verb = "updated"
    else:
        prompt_id = f"pr-{uuid4().hex[:6]}"
        doc = {
            "id": prompt_id,
            "title": name,
            "topic": name,
            "usageCount": 0,
            "sections": [],
            "userSections": [],
            "humanInputs": [],
            "mdContent": content,
            "format": "md",
        }
        verb = "created"

    doc["lastModified"] = datetime.utcnow().isoformat()
    _write_doc(doc, old_path=existing.get("__path") if existing else None)
    out.success(f"Prompt '{name}' (id {prompt_id}) {verb}!")
    _prompt_cloud_sync(doc, "UPDATE" if existing else "ADD")


@prompts.command()
@requires_auth
@click.argument('name')
@click.argument('new_name')
def copy(name, new_name):
    """
    Copy a prompt under a new name.

    OPERATION command - duplicates a prompt in the my_prompts library with a
    fresh id, so the copy can be edited independently of the original.

    Examples:
      ecan prompts copy travel_agent0 travel_agent1
    """
    out = get_output()

    src = _find_by_title(name)
    if not src:
        out.error(f"Prompt not found: {name}")
        raise SystemExit(1)

    target = str(new_name or "").strip().lower()
    if any(str(d.get("title") or "").strip().lower() == target
           for d in _load_prompt_docs()):
        out.error(f"Prompt already exists: {new_name}")
        raise SystemExit(1)

    doc = {k: v for k, v in src.items() if k != "__path"}
    doc["id"] = f"pr-{uuid4().hex[:6]}"
    doc["title"] = new_name
    doc["topic"] = new_name
    doc["usageCount"] = 0
    doc["lastModified"] = datetime.utcnow().isoformat()
    _write_doc(doc)
    out.success(f"Prompt '{src.get('title')}' copied to '{new_name}' (id {doc['id']})!")
    _prompt_cloud_sync(doc, "ADD")


@prompts.command()
@requires_auth
@click.argument('name')
@click.option('--force', '-f', is_flag=True,
              help='Skip confirmation prompt')
def remove(name, force):
    """
    Delete a prompt.

    OPERATION command - permanently removes a prompt from the my_prompts library.

    Examples:
      ecan prompts remove travel_agent0      # With confirmation
      ecan prompts remove travel_agent0 -f   # Skip confirmation
    """
    out = get_output()

    doc = _find_by_title(name)
    if not doc:
        out.error(f"Prompt not found: {name}")
        raise SystemExit(1)

    if not force and not out.confirm(f"Delete prompt '{doc.get('title')}' (id {doc.get('id')})?"):
        return

    path = doc.get("__path")
    try:
        if path:
            Path(path).unlink()
    except Exception as exc:
        out.error(f"Failed to delete prompt: {exc}")
        raise SystemExit(1)
    out.success(f"Prompt '{doc.get('title')}' deleted!")
    _prompt_cloud_sync({"id": doc.get("id"), "title": doc.get("title")}, "DELETE")


@prompts.command()
@requires_auth
@click.argument('name')
@click.option('--new-name', '-N', help='Rename the prompt (its title)')
@click.option('--content', '-c', help='Replace content (use \\n for newlines)')
@click.option('--file', '-f', 'file_path', type=click.Path(exists=True),
              help='Replace content from a file')
def update(name, new_name, file_path, content):
    """
    Update a prompt in place.

    OPERATION command - changes a prompt's title and/or content while KEEPING
    its id, so agents that reference it stay wired up. Requires auth.

    Examples:
      ecan prompts update greeting -c "Hi there!"
      ecan prompts update greeting -N welcome
      ecan prompts update travel_agent0 -f ./new.md
    """
    out = get_output()

    doc = _find_by_title(name)
    if not doc:
        out.error(f"Prompt not found: {name}")
        raise SystemExit(1)

    if file_path:
        content = Path(file_path).read_text(encoding="utf-8")
    if not new_name and content is None:
        out.warning("Nothing to update (pass --new-name and/or --content/--file)")
        return

    old_path = doc.get("__path")
    updated = {k: v for k, v in doc.items() if k != "__path"}
    if new_name:
        target = str(new_name).strip().lower()
        if any(str(d.get("title") or "").strip().lower() == target and d.get("id") != updated.get("id")
               for d in _load_prompt_docs()):
            out.error(f"Prompt already exists: {new_name}")
            raise SystemExit(1)
        updated["title"] = new_name
        updated["topic"] = new_name
    if content is not None:
        updated["mdContent"] = content
        updated["format"] = "md"
    updated["lastModified"] = datetime.utcnow().isoformat()

    _write_doc(updated, old_path=old_path)
    out.success(f"Prompt updated (id {updated.get('id')})!")
    _prompt_cloud_sync(updated, "UPDATE")


def _prompt_cloud_sync(doc: Dict[str, Any], op_name: str) -> None:
    """Best-effort push to the cloud prompt store via the offline sync queue,
    mirroring ``ecan skills``. Never fails the local write."""
    try:
        from ..base.sync import cloud_sync
        from agent.cloud_api.constants import DataType, Operation
        payload = {k: v for k, v in (doc or {}).items() if k != "__path"}
        cloud_sync(DataType.PROMPT, payload, getattr(Operation, op_name))
    except Exception:
        pass


@prompts.command()
@requires_auth
@click.argument('name')
@click.option('--editor', '-e', is_flag=True,
              help='Edit with default editor ($EDITOR)')
def edit(name, editor):
    """
    Edit a prompt.

    OPERATION command - opens a prompt's JSON file in the editor.

    Examples:
      ecan prompts edit travel_agent0 -e
    """
    out = get_output()

    doc = _find_by_title(name)
    if not doc or not doc.get("__path"):
        out.error(f"Prompt not found: {name}")
        raise SystemExit(1)
    prompt_file = doc["__path"]

    if editor:
        editor_cmd = os.environ.get('EDITOR', 'vim')
        import subprocess
        subprocess.run([editor_cmd, str(prompt_file)])
    else:
        out.info("Use 'ecan prompts edit -e' to edit in your editor")
        out.print(f"Prompt file: {prompt_file}")


@prompts.command()
@click.argument('name')
@click.argument('args', nargs=-1)
def run(name, args):
    """
    Run a prompt with arguments.

    QUERY command - displays prompt content with placeholders replaced.

    Placeholders: {0}, {1}, ... or {arg0}, {arg1}, ...

    Examples:
      ecan prompts run greeting John
    """
    out = get_output()

    doc = _find_by_title(name)
    if not doc:
        out.error(f"Prompt not found: {name}")
        raise SystemExit(1)

    content = _construct_content(doc)
    for i, arg in enumerate(args):
        content = content.replace(f"{{{i}}}", arg)
        content = content.replace(f"{{arg{i}}}", arg)

    out.title(f"Prompt: {doc.get('title')}")
    out.print(content)
