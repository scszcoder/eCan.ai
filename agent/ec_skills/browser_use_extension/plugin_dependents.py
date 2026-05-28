"""
Plugin Dependents — scan local skill diagrams for browser-automation nodes
that reference a plugin bundle.

Used by the installer's uninstall/disable flow to refuse (or warn loudly)
when removing a bundle still referenced from a node's ``hookBundles`` field.

Scan scope
----------
- ``<repo_root>/my_skills/`` and ``<repo_root>/skills/`` — the on-disk
  layouts shipped with the app.
- ``<appdata>/my_skills/`` if the install lives in a user data dir.

Skill diagrams are JSON files under ``<skill_dir>/diagram_dir/<skill>.json``.
Each diagram has a ``workFlow.nodes`` list; browser-automation nodes carry
``type: "browser-automation"`` and their ``data.inputsValues.hookBundles.content``
is a JSON-string list of ``{path, enabled?, config?}`` entries. We treat
``path`` as the bundle reference.

Match rule
----------
A node depends on bundle ``X`` when any entry in its hookBundles list has
``path`` equal to either ``X`` (in-tree shorthand) or ``<install_path>/X``
(absolute). For Phase 1 we match on the bare basename — same heuristic the
hook_loader uses to resolve in-tree paths.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

logger = logging.getLogger("eCan")


@dataclass(frozen=True)
class Dependent:
    skill_id: str
    skill_name: str
    skill_path: str
    node_id: str
    node_name: str


def _candidate_skill_roots() -> list[Path]:
    """Return likely roots that contain skill diagrams.

    Order: project ``my_skills`` and ``skills`` first (dev/in-repo layout),
    then per-user counterparts under appdata.
    """
    roots: list[Path] = []
    try:
        # Repo root is two levels up from this file's package, but we don't
        # want to encode that — just use CWD when in dev, plus appdata.
        cwd = Path.cwd()
        for sub in ("my_skills", "skills"):
            p = cwd / sub
            if p.is_dir():
                roots.append(p)
    except Exception:
        pass

    try:
        from config.envi import getECBotDataHome
        appdata = Path(getECBotDataHome())
        for sub in ("my_skills", "skills"):
            p = appdata / sub
            if p.is_dir() and p not in roots:
                roots.append(p)
    except Exception:
        pass

    return roots


def _iter_skill_diagrams(roots: Iterable[Path]) -> Iterable[tuple[Path, dict]]:
    """Yield (path, parsed_json) for each well-formed skill diagram."""
    for root in roots:
        if not root.is_dir():
            continue
        try:
            for skill_dir in sorted(root.iterdir()):
                if not skill_dir.is_dir():
                    continue
                diagram_dir = skill_dir / "diagram_dir"
                if not diagram_dir.is_dir():
                    continue
                # Prefer the non-_bundle.json file; the bundle file is a
                # packaged variant of the same content.
                for diagram_file in sorted(diagram_dir.glob("*.json")):
                    if diagram_file.stem.endswith("_bundle"):
                        continue
                    try:
                        data = json.loads(diagram_file.read_text(encoding="utf-8"))
                    except Exception as e:
                        logger.debug(
                            f"[PluginDependents] skipping unparseable diagram "
                            f"{diagram_file}: {e}"
                        )
                        continue
                    if not isinstance(data, dict):
                        continue
                    yield diagram_file, data
        except Exception as e:
            logger.debug(f"[PluginDependents] root scan failed for {root}: {e}")


def _extract_hook_bundles(node: dict) -> list[dict]:
    """Pull and parse the hookBundles JSON-string from a browser-automation node.

    The field shape in the skill JSON is:
        node.data.inputsValues.hookBundles = {type: "constant", content: "[{...}]"}
    Content can be either a JSON string (canonical) or already a list (some
    older saves). Returns [] when the field is absent or malformed.
    """
    data = node.get("data") if isinstance(node, dict) else None
    if not isinstance(data, dict):
        return []
    inputs = data.get("inputsValues")
    if not isinstance(inputs, dict):
        return []
    hb = inputs.get("hookBundles")
    if not isinstance(hb, dict):
        return []
    content = hb.get("content")
    if isinstance(content, list):
        return [e for e in content if isinstance(e, dict)]
    if isinstance(content, str) and content.strip():
        try:
            parsed = json.loads(content)
        except Exception:
            return []
        if isinstance(parsed, list):
            return [e for e in parsed if isinstance(e, dict)]
    return []


def _bundle_ref_matches(entry: dict, target: str) -> bool:
    """Treat target as the bundle's bare name; match against entry['path']."""
    path = entry.get("path")
    if not isinstance(path, str) or not path:
        return False
    # Bare name match (in-tree shorthand).
    if path == target:
        return True
    # Absolute path or relative subpath — match by basename.
    try:
        return Path(path).name == target
    except Exception:
        return False


def _walk_nodes(diagram: dict) -> Iterable[dict]:
    """Yield every node in the diagram, recursing into loop/block children."""
    workflow = diagram.get("workFlow") if isinstance(diagram, dict) else None
    if not isinstance(workflow, dict):
        return
    stack: list = list(workflow.get("nodes") or [])
    while stack:
        node = stack.pop()
        if not isinstance(node, dict):
            continue
        yield node
        # Loop / container nodes carry their children under "blocks".
        children = node.get("blocks")
        if isinstance(children, list):
            stack.extend(children)


def find_dependents(bundle_name: str) -> list[Dependent]:
    """Return every browser-automation node that references ``bundle_name``."""
    out: list[Dependent] = []
    for diagram_path, diagram in _iter_skill_diagrams(_candidate_skill_roots()):
        skill_id = str(diagram.get("skillId") or "")
        skill_name = str(diagram.get("skillName") or diagram_path.parent.parent.name)
        for node in _walk_nodes(diagram):
            if str(node.get("type") or "") != "browser-automation":
                continue
            entries = _extract_hook_bundles(node)
            if not entries:
                continue
            if any(_bundle_ref_matches(e, bundle_name) for e in entries):
                node_data = node.get("data") if isinstance(node.get("data"), dict) else {}
                out.append(Dependent(
                    skill_id=skill_id,
                    skill_name=skill_name,
                    skill_path=str(diagram_path),
                    node_id=str(node.get("id") or ""),
                    node_name=str((node_data.get("title") or "")),
                ))
    return out


def has_dependents(bundle_name: str) -> bool:
    return bool(find_dependents(bundle_name))


__all__ = ["Dependent", "find_dependents", "has_dependents"]
