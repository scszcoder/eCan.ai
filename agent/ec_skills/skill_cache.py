"""
Persistent cache for resolved skill payloads.

Phase A1 (2026-05-17). Customer with 10 agents on a low-end CPU was seeing
15-30 s startup freezes during agent skill build (see memory
project-startup-apphang). The expensive per-skill work is:

  1. Walking skill folders + listing files
  2. Reading + JSON-parsing diagram_dir/*.json (core + bundle)
  3. Reading data_mapping.json
  4. flowgram2langgraph_v2(core_dict, bundle_dict)  --- the LangGraph build
  5. CompiledStateGraph compile (cheap relative to #4)
  6. Pydantic EC_Skill construction

This cache eliminates #1-#3 on warm runs. We pickle only the parsed dicts
(core, bundle, mapping) keyed by a content hash of the skill source. We do
NOT pickle the StateGraph or CompiledStateGraph — they hold closures, node
functions, and a checkpointer that don't round-trip cleanly across LangGraph
versions, and a cache-miss-disguised-as-hit on those would be much worse
than the 6-10 s of file I/O we save.

The remaining heavy work (#4-#6) still runs per skill, but now on the Phase B
ThreadPool so it does not block the Qt UI thread.

Disable with `ECAN_SKILL_CACHE=0` to force full reload (debugging or after a
LangGraph upgrade if anything misbehaves).
"""

from __future__ import annotations

import hashlib
import os
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from utils.logger_helper import logger_helper as logger

SCHEMA_VERSION = 1
_CACHE_DIR_NAME = "skill_cache"
_HASH_INCLUDE_SUFFIXES = (".json", ".py", ".md", ".yaml", ".yml", ".txt")


@dataclass
class ResolvedPayload:
    """Inputs to the expensive build step, captured at first load."""
    schema_version: int
    core_dict: Dict[str, Any]
    bundle_dict: Optional[Dict[str, Any]]
    mapping_rules: Optional[Dict[str, Any]]
    core_path_str: str  # str of the diagram core .json path used at load time


def _enabled() -> bool:
    return os.environ.get("ECAN_SKILL_CACHE", "1") != "0"


def _cache_root() -> Optional[Path]:
    try:
        from utils.path_manager import PathManager
        pm = PathManager()
        root = Path(pm.user_data_path) / _CACHE_DIR_NAME
        root.mkdir(parents=True, exist_ok=True)
        return root
    except Exception as e:
        logger.debug(f"[skill_cache] cache root unavailable: {e}")
        return None


def _content_hash(skill_root: Path) -> Optional[str]:
    """Hash everything that contributes to the resolved payload.

    Uses (relative-path, size, mtime) per file rather than reading bytes —
    fast to compute, sensitive enough to catch any user edit. Includes both
    diagram_dir and code_dir contents so code-skill changes also invalidate.
    """
    try:
        h = hashlib.sha256()
        h.update(f"schema={SCHEMA_VERSION}\n".encode())

        def feed(file_path: Path) -> None:
            try:
                stat = file_path.stat()
                rel = file_path.relative_to(skill_root).as_posix()
                h.update(f"{rel}|{stat.st_size}|{int(stat.st_mtime)}\n".encode())
            except Exception:
                pass

        roots_to_scan = [
            skill_root / "diagram_dir",
            skill_root / "code_dir",
            skill_root / "code_skill",
        ]
        for sub in roots_to_scan:
            if sub.exists():
                for p in sorted(sub.rglob("*")):
                    if p.is_file() and p.suffix.lower() in _HASH_INCLUDE_SUFFIXES:
                        feed(p)

        mapping_file = skill_root / "data_mapping.json"
        if mapping_file.exists():
            feed(mapping_file)

        return h.hexdigest()[:16]
    except Exception as e:
        logger.debug(f"[skill_cache] hash failed for {skill_root}: {e}")
        return None


def _cache_path_for(skill_root: Path, digest: str) -> Optional[Path]:
    root = _cache_root()
    if root is None:
        return None
    return root / f"{skill_root.name}__{digest}.pkl"


def load(skill_root: Path) -> Optional[ResolvedPayload]:
    """Return cached payload if hash matches; else None."""
    if not _enabled():
        return None
    digest = _content_hash(skill_root)
    if digest is None:
        return None
    path = _cache_path_for(skill_root, digest)
    if path is None or not path.exists():
        return None
    try:
        with path.open("rb") as f:
            payload = pickle.load(f)
        if not isinstance(payload, ResolvedPayload):
            return None
        if payload.schema_version != SCHEMA_VERSION:
            return None
        logger.debug(f"[skill_cache] HIT  {skill_root.name} ({digest})")
        return payload
    except Exception as e:
        logger.debug(f"[skill_cache] load failed for {skill_root.name}: {e}")
        return None


def store(skill_root: Path, payload: ResolvedPayload) -> None:
    """Write payload to cache and prune any stale digests for this skill."""
    if not _enabled():
        return
    digest = _content_hash(skill_root)
    if digest is None:
        return
    root = _cache_root()
    if root is None:
        return
    # Prune stale digests so the cache dir stays bounded per skill.
    prefix = f"{skill_root.name}__"
    try:
        for old in root.glob(f"{prefix}*.pkl"):
            if not old.name.endswith(f"{digest}.pkl"):
                try:
                    old.unlink()
                except Exception:
                    pass
    except Exception:
        pass

    path = root / f"{prefix}{digest}.pkl"
    try:
        # Write to tmp then rename so a crashed write never leaves a half-file
        # that load() would happily unpickle into garbage.
        tmp = path.with_suffix(".pkl.tmp")
        with tmp.open("wb") as f:
            pickle.dump(payload, f, protocol=pickle.HIGHEST_PROTOCOL)
        tmp.replace(path)
        logger.debug(f"[skill_cache] STORE {skill_root.name} ({digest})")
    except Exception as e:
        logger.debug(f"[skill_cache] store failed for {skill_root.name}: {e}")
