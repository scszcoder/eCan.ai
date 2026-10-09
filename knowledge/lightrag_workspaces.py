"""
Filesystem layout of LightRAG workspaces (knowledge bases) on the desktop.

LightRAG's file storages keep each workspace under ``WORKING_DIR/<workspace>``
where ``WORKING_DIR`` is the ``rag_storage`` directory. These helpers are the
one place that maps a workspace name to a path, so the GUI handlers stop
re-deriving it with ``split('/')`` (which broke on Windows paths) and stop
touching other workspaces' data.
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any, List, Optional

# Directory names under rag_storage that are not workspaces.
SYSTEM_DIRS = {'inputs', 'outputs', 'logs', '.git', '__pycache__', 'rag_storage', 'tiktoken', 'cache'}

HISTORY_KINDS = ('input', 'conversation')


def rag_storage_root(working_dir: str) -> Path:
    """The rag_storage directory, even if WORKING_DIR points inside it."""
    p = Path(working_dir)
    for candidate in (p, *p.parents):
        if candidate.name == 'rag_storage':
            return candidate
    return p


def validate_workspace_name(name: Optional[str]) -> str:
    """Reject names that could escape rag_storage or collide with system dirs."""
    ws = (name or '').strip()
    if not ws:
        raise ValueError('workspace name is required')
    if ws in ('.', '..') or any(c in ws for c in '/\\:*?"<>|') or ws.startswith('.'):
        raise ValueError(f'invalid workspace name: {ws!r}')
    if ws in SYSTEM_DIRS:
        raise ValueError(f'reserved workspace name: {ws!r}')
    return ws


def workspace_dir(working_dir: str, name: str) -> Path:
    root = rag_storage_root(working_dir).resolve()
    path = (root / validate_workspace_name(name)).resolve()
    if path.parent != root:
        raise ValueError(f'workspace path escapes rag_storage: {name!r}')
    return path


def list_workspaces(working_dir: str) -> List[str]:
    root = rag_storage_root(working_dir)
    if not root.is_dir():
        return []
    names = [
        item.name for item in root.iterdir()
        if item.is_dir() and item.name not in SYSTEM_DIRS and not item.name.startswith('.')
    ]
    return sorted(names, key=str.lower)


def delete_workspace_files(working_dir: str, name: str, legacy_root: Optional[str] = None) -> List[str]:
    """Delete one workspace's directory. Returns the paths removed.

    ``legacy_root`` is the user data dir, where older builds created
    ``lightrag_<name>`` folders.
    """
    removed: List[str] = []
    targets = [workspace_dir(working_dir, name)]
    if legacy_root:
        targets.append(Path(legacy_root) / f'lightrag_{validate_workspace_name(name)}')
    for target in targets:
        if target.is_dir():
            shutil.rmtree(target)
            removed.append(str(target))
    return removed


def history_path(working_dir: str, workspace: str, kind: str) -> Path:
    if kind not in HISTORY_KINDS:
        raise ValueError(f'unknown history kind: {kind}')
    return workspace_dir(working_dir, workspace) / f'ecan_{kind}_history.json'


def _legacy_history_path(working_dir: str, kind: str) -> Path:
    return rag_storage_root(working_dir) / f'lightrag_{kind}_history.json'


def read_history(working_dir: str, workspace: str, kind: str, default_workspace: str = '') -> List[Any]:
    """History list for one workspace.

    Older builds kept a single file for all workspaces in rag_storage; it is
    shown for the default workspace only, until that workspace saves its own.
    """
    path = history_path(working_dir, workspace, kind)
    if not path.exists() and workspace == default_workspace:
        path = _legacy_history_path(working_dir, kind)
    if not path.exists():
        return []
    try:
        content = path.read_text(encoding='utf-8').strip()
        data = json.loads(content) if content else []
    except (OSError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def write_history(working_dir: str, workspace: str, kind: str, items: List[Any]) -> Path:
    path = history_path(working_dir, workspace, kind)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(tmp, path)
    return path
