#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Resolve an id-or-name identifier to a concrete record id.

The cloud-side agent proposes CLI commands using the human name the user
mentioned (e.g. `ecan agents update "Support Bot" -d "..."`) because it does
not know local ids. These helpers let the CLI accept either an id or a name and
resolve it against the local DB before acting.
"""

from typing import Optional


def resolve_entity_id(service, identifier: str, kind: str) -> Optional[str]:
    """Resolve *identifier* (an id or a name) to a concrete id.

    Args:
        service: DBAgentService, DBTaskService, or DBSkillService.
        identifier: an id or a (case-insensitive) name.
        kind: 'agent', 'task', or 'skill'.

    Returns:
        The resolved id, or None if nothing matches.

    Raises:
        ValueError: if a name matches more than one record.
    """
    if kind == "agent":
        query = service.query_agents
    elif kind == "skill":
        query = service.query_skills
    else:
        query = service.query_tasks

    # 1) exact id
    r = query(id=identifier)
    rows = (r.get("data") or []) if isinstance(r, dict) else []
    if rows:
        return rows[0].get("id")

    # 2) by name (query is fuzzy, so narrow to an exact case-insensitive match)
    r = query(name=identifier)
    rows = (r.get("data") or []) if isinstance(r, dict) else []
    target = str(identifier).strip().lower()
    exact = [x for x in rows if str(x.get("name", "")).strip().lower() == target]
    pool = exact or rows
    if len(pool) == 1:
        return pool[0].get("id")
    if len(pool) > 1:
        names = ", ".join(f"{x.get('name')} ({x.get('id')})" for x in pool[:10])
        raise ValueError(f"'{identifier}' matches {len(pool)} {kind}s: {names}. Use the id.")
    return None
