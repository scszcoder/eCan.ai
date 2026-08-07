"""
Filtered queries over AgentDirectory — "find any agent with skill X".

Phase 3 of the discovery rework. Per-agent advertising landed in Phase 1
(zeroconf) and Phase 2 (cloud), so the directory already knows what each
peer agent can do (TXT/cloud ``skills`` field). This module adds the
search API that's the headline of Phase 3:

    find_agents(skill="live_chat") → [AgentEndpoint, ...]
    find_agents(role="manager", reachable=True) → [...]
    find_agents(skill_any=("live_chat", "email"), org="songc_yahoo_com")

Sorted by transport preference (LAN-direct before WAN-relay), then by
``name`` for deterministic UI ordering.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Sequence

from agent.a2a.discovery.directory import AgentDirectory, AgentEndpoint, get_directory


def _transport_rank(ep: AgentEndpoint) -> int:
    """Lower = preferred. LAN-direct (0) > WAN-only (1) > stale (2)."""
    if ep.is_lan_reachable:
        return 0
    if ep.wan_relay_channel:
        return 1
    if ep.lan_url:
        return 2   # advertised LAN but not recently seen
    return 3       # GC candidate


def _matches_skill_any(ep: AgentEndpoint, wanted: Sequence[str]) -> bool:
    if not wanted:
        return True
    eps = {s.strip().lower() for s in ep.skills if s}
    want = {s.strip().lower() for s in wanted if s}
    return bool(eps & want)


def _matches_skill_all(ep: AgentEndpoint, wanted: Sequence[str]) -> bool:
    if not wanted:
        return True
    eps = {s.strip().lower() for s in ep.skills if s}
    want = {s.strip().lower() for s in wanted if s}
    return want.issubset(eps)


def _matches_role(ep: AgentEndpoint, role: Optional[str]) -> bool:
    if not role:
        return True
    return (ep.role or "").strip().lower() == role.strip().lower()


def _matches_name_contains(ep: AgentEndpoint, needle: Optional[str]) -> bool:
    if not needle:
        return True
    return needle.strip().lower() in (ep.name or "").lower()


def _matches_machine_id(ep: AgentEndpoint, machine_id: Optional[str]) -> bool:
    if not machine_id:
        return True
    return ep.machine_id == machine_id


def _matches_org(ep: AgentEndpoint, org: Optional[str]) -> bool:
    if not org:
        return True
    return ep.org == org


def find_agents(
    *,
    skill: Optional[str] = None,
    skill_any: Optional[Sequence[str]] = None,
    skill_all: Optional[Sequence[str]] = None,
    role: Optional[str] = None,
    name_contains: Optional[str] = None,
    machine_id: Optional[str] = None,
    org: Optional[str] = None,
    reachable: bool = False,
    transport: Optional[str] = None,
    exclude_self: bool = True,
    limit: Optional[int] = None,
    directory: Optional[AgentDirectory] = None,
) -> list[AgentEndpoint]:
    """Search the AgentDirectory with one or more filters AND-ed together.

    Args:
        skill: convenience — shorthand for ``skill_any=(skill,)``
        skill_any: match any of these (set-intersect with the agent's skills)
        skill_all: agent must have ALL of these skills
        role: exact-match role string
        name_contains: case-insensitive substring of ``name``
        machine_id: restrict to agents hosted on this machine
        org: restrict to a specific org (default: any)
        reachable: when True, drop entries with no live transport
        transport: when set ("lan" or "wan"), restrict to that transport
        exclude_self: omit agents hosted on this machine (default True)
        limit: cap the result list
        directory: optional explicit directory (defaults to singleton)

    Returns: list of matching endpoints, sorted by transport preference then name.
    """
    d = directory or get_directory()
    candidates = d.list_agents(exclude_self=exclude_self)

    # Normalize skill filters: ``skill=`` shortcut folds into ``skill_any``.
    wanted_any = list(skill_any or [])
    if skill:
        wanted_any.append(skill)

    out: list[AgentEndpoint] = []
    for ep in candidates:
        if not _matches_org(ep, org):
            continue
        if not _matches_role(ep, role):
            continue
        if not _matches_name_contains(ep, name_contains):
            continue
        if not _matches_machine_id(ep, machine_id):
            continue
        if wanted_any and not _matches_skill_any(ep, wanted_any):
            continue
        if skill_all and not _matches_skill_all(ep, skill_all):
            continue

        rank = _transport_rank(ep)
        if reachable and rank >= 2:
            continue
        if transport == "lan" and rank != 0:
            continue
        if transport == "wan":
            if not ep.wan_relay_channel:
                continue

        out.append(ep)

    out.sort(key=lambda e: (_transport_rank(e), (e.name or "").lower(), e.agent_id))
    if limit is not None and limit >= 0:
        out = out[:limit]
    return out


def find_one_agent(**kwargs) -> Optional[AgentEndpoint]:
    """Convenience for "I just need one matching agent" — returns first match."""
    kwargs.setdefault("limit", 1)
    hits = find_agents(**kwargs)
    return hits[0] if hits else None


def list_skills(
    *, org: Optional[str] = None, directory: Optional[AgentDirectory] = None
) -> dict[str, int]:
    """Return ``{skill_name: count_of_agents_offering_it}`` across the directory.

    Useful for UI dropdowns / autocompletion ("what skills are available
    across our fleet right now?").
    """
    d = directory or get_directory()
    counts: dict[str, int] = {}
    for ep in d.list_agents(exclude_self=False):
        if org and ep.org != org:
            continue
        for s in ep.skills:
            if not s:
                continue
            counts[s] = counts.get(s, 0) + 1
    return counts
