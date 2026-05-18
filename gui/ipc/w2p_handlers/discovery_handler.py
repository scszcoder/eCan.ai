"""IPC handlers for the agent discovery subsystem (Phase 3).

Frontend API surface:
    - discovery.list_agents          → snapshot of known agents (LAN + WAN)
    - discovery.list_nodes           → snapshot of known eCan nodes
    - discovery.find_agents          → filtered query (skill / role / name)
    - discovery.list_skills          → "what skills are available across the fleet"
    - discovery.transport_for        → which transport would be used for an agent_id
    - discovery.get_status           → diagnostics (LAN active, WAN active, counts)
    - discovery.send_to_agent        → fire an A2A payload at one peer
    - discovery.send_to_group        → fanout to many peers
    - discovery.send_to_skill        → find-then-send convenience
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional

from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import IPCRequest, IPCResponse, create_error_response, create_success_response
from utils.logger_helper import logger_helper as logger


def _endpoint_to_dict(ep) -> dict:
    return {
        "agent_id": ep.agent_id,
        "machine_id": ep.machine_id,
        "org": ep.org,
        "name": ep.name,
        "role": ep.role,
        "skills": list(ep.skills),
        "lan_url": ep.lan_url,
        "lan_last_seen": ep.lan_last_seen,
        "wan_relay_channel": ep.wan_relay_channel,
        "wan_last_seen": ep.wan_last_seen,
    }


def _outcome_to_dict(outcome) -> dict:
    return {
        "transport": outcome.transport,
        "success": bool(outcome.success),
        "error": outcome.error,
        "response": outcome.response,
    }


def _run_async(coro):
    """Run an async coroutine from a sync IPC handler.

    Uses the app's running loop if we can find it (qasync exposes one),
    otherwise spins up a temporary loop. Either way the call is blocking
    for the duration of the coro.
    """
    try:
        # Try to dispatch on the running loop without blocking it.
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            fut = asyncio.run_coroutine_threadsafe(coro, loop)
            return fut.result(timeout=60)
        return loop.run_until_complete(coro)
    except RuntimeError:
        # No loop in this thread — make one.
        return asyncio.new_event_loop().run_until_complete(coro)


# ============================================================================
# Read-side: list / find / status
# ============================================================================

@IPCHandlerRegistry.handler('discovery.list_agents')
def handle_list_agents(request: IPCRequest, params: Optional[Any] = None) -> IPCResponse:
    try:
        from agent.a2a.discovery import get_directory
        d = get_directory()
        include_self = bool((params or {}).get("include_self"))
        agents = d.list_agents(exclude_self=not include_self)
        return create_success_response(request, {
            "agents": [_endpoint_to_dict(ep) for ep in agents],
            "total": len(agents),
        })
    except Exception as e:
        logger.error(f"[discovery] list_agents failed: {e}", exc_info=True)
        return create_error_response(request, "DISCOVERY_ERROR", str(e))


@IPCHandlerRegistry.handler('discovery.list_nodes')
def handle_list_nodes(request: IPCRequest, params: Optional[Any] = None) -> IPCResponse:
    try:
        from agent.a2a.discovery import get_directory
        d = get_directory()
        include_self = bool((params or {}).get("include_self"))
        nodes = d.list_nodes(exclude_self=not include_self)
        return create_success_response(request, {
            "nodes": [
                {
                    "machine_id": n.machine_id,
                    "machine_name": n.machine_name,
                    "host": n.lan_host,
                    "role": n.role,
                    "os": n.os,
                    "arch": n.arch,
                    "ecan_ver": n.ecan_ver,
                    "agent_count": n.agent_count,
                    "api_port": n.api_port,
                    "last_seen": n.lan_last_seen,
                }
                for n in nodes
            ],
            "total": len(nodes),
        })
    except Exception as e:
        logger.error(f"[discovery] list_nodes failed: {e}", exc_info=True)
        return create_error_response(request, "DISCOVERY_ERROR", str(e))


@IPCHandlerRegistry.handler('discovery.find_agents')
def handle_find_agents(request: IPCRequest, params: Optional[Any] = None) -> IPCResponse:
    """Filtered search.

    Accepted params (all optional):
        skill: str            — single-skill shorthand
        skill_any: list[str]  — match any of these skills
        skill_all: list[str]  — agent must have all these skills
        role: str
        name_contains: str
        machine_id: str
        org: str
        reachable: bool       — drop entries with no live transport
        transport: "lan"|"wan"
        exclude_self: bool    — default True
        limit: int
    """
    try:
        from agent.a2a.discovery.query import find_agents
        p = params or {}
        hits = find_agents(
            skill=p.get("skill"),
            skill_any=p.get("skill_any") or None,
            skill_all=p.get("skill_all") or None,
            role=p.get("role"),
            name_contains=p.get("name_contains"),
            machine_id=p.get("machine_id"),
            org=p.get("org"),
            reachable=bool(p.get("reachable", False)),
            transport=p.get("transport"),
            exclude_self=bool(p.get("exclude_self", True)),
            limit=p.get("limit"),
        )
        return create_success_response(request, {
            "agents": [_endpoint_to_dict(ep) for ep in hits],
            "total": len(hits),
        })
    except Exception as e:
        logger.error(f"[discovery] find_agents failed: {e}", exc_info=True)
        return create_error_response(request, "DISCOVERY_ERROR", str(e))


@IPCHandlerRegistry.handler('discovery.list_skills')
def handle_list_skills(request: IPCRequest, params: Optional[Any] = None) -> IPCResponse:
    """Return ``{skill_name: count}`` across all known agents in the org."""
    try:
        from agent.a2a.discovery.query import list_skills
        org = (params or {}).get("org")
        counts = list_skills(org=org)
        return create_success_response(request, {
            "skills": counts,
            "total": len(counts),
        })
    except Exception as e:
        logger.error(f"[discovery] list_skills failed: {e}", exc_info=True)
        return create_error_response(request, "DISCOVERY_ERROR", str(e))


@IPCHandlerRegistry.handler('discovery.transport_for')
def handle_transport_for(request: IPCRequest, params: Optional[Any] = None) -> IPCResponse:
    try:
        from agent.a2a.discovery.router import transport_for
        agent_id = (params or {}).get("agent_id") or ""
        if not agent_id:
            return create_error_response(request, "INVALID_PARAMS", "agent_id is required")
        return create_success_response(request, {
            "agent_id": agent_id,
            "transport": transport_for(agent_id),
        })
    except Exception as e:
        logger.error(f"[discovery] transport_for failed: {e}", exc_info=True)
        return create_error_response(request, "DISCOVERY_ERROR", str(e))


@IPCHandlerRegistry.handler('discovery.get_status')
def handle_get_status(request: IPCRequest, params: Optional[Any] = None) -> IPCResponse:
    """Diagnostics — what's running and how many peers we see."""
    try:
        from agent.a2a.discovery import get_directory
        from agent.a2a.discovery.zeroconf_service import get_lan_discovery
        from agent.a2a.discovery.cloud_directory import get_cloud_directory

        d = get_directory()
        snap = d.snapshot()
        lan = get_lan_discovery()
        cloud = get_cloud_directory()
        return create_success_response(request, {
            "self_machine_id": snap.get("self_machine_id"),
            "lan_active": lan is not None,
            "wan_active": cloud is not None,
            "nodes_known": len(snap.get("nodes") or []),
            "agents_known": len(snap.get("agents") or []),
            "snapshot": snap,
        })
    except Exception as e:
        logger.error(f"[discovery] get_status failed: {e}", exc_info=True)
        return create_error_response(request, "DISCOVERY_ERROR", str(e))


# ============================================================================
# Write-side: send / fanout / find-then-send
# ============================================================================

@IPCHandlerRegistry.handler('discovery.send_to_agent')
def handle_send_to_agent(request: IPCRequest, params: Optional[Any] = None) -> IPCResponse:
    """Send one A2A payload to one agent_id. Picks LAN-direct or WAN-relay."""
    try:
        from agent.a2a.discovery.router import send_to_agent
        p = params or {}
        agent_id = p.get("agent_id") or ""
        payload = p.get("payload") or {}
        if not agent_id:
            return create_error_response(request, "INVALID_PARAMS", "agent_id is required")
        from_agent_id = p.get("from_agent_id")
        timeout = float(p.get("timeout") or 15.0)
        outcome = _run_async(send_to_agent(
            agent_id, payload, from_agent_id=from_agent_id, timeout=timeout
        ))
        return create_success_response(request, _outcome_to_dict(outcome))
    except Exception as e:
        logger.error(f"[discovery] send_to_agent failed: {e}", exc_info=True)
        return create_error_response(request, "DISCOVERY_ERROR", str(e))


@IPCHandlerRegistry.handler('discovery.send_to_group')
def handle_send_to_group(request: IPCRequest, params: Optional[Any] = None) -> IPCResponse:
    """Fanout to an explicit list of agent_ids."""
    try:
        from agent.a2a.discovery.group import send_to_group
        p = params or {}
        agent_ids = list(p.get("agent_ids") or [])
        payload = p.get("payload") or {}
        if not agent_ids:
            return create_error_response(request, "INVALID_PARAMS", "agent_ids is required (non-empty list)")
        from_agent_id = p.get("from_agent_id")
        timeout = float(p.get("timeout") or 15.0)
        max_concurrency = int(p.get("max_concurrency") or 8)
        report = _run_async(send_to_group(
            agent_ids, payload,
            from_agent_id=from_agent_id,
            timeout=timeout,
            max_concurrency=max_concurrency,
        ))
        return create_success_response(request, {
            "summary": report.summary(),
            "succeeded": report.succeeded,
            "failed": report.failed,
            "per_agent": {aid: _outcome_to_dict(o) for aid, o in report.per_agent.items()},
            "targets": [_endpoint_to_dict(ep) for ep in report.targets],
        })
    except Exception as e:
        logger.error(f"[discovery] send_to_group failed: {e}", exc_info=True)
        return create_error_response(request, "DISCOVERY_ERROR", str(e))


@IPCHandlerRegistry.handler('discovery.send_to_skill')
def handle_send_to_skill(request: IPCRequest, params: Optional[Any] = None) -> IPCResponse:
    """Find agents offering ``skill`` and dispatch.

    mode: "any" (first reachable) | "all" (broadcast) | "n=K" (top K)
    """
    try:
        from agent.a2a.discovery.group import send_to_skill
        p = params or {}
        skill = p.get("skill") or ""
        payload = p.get("payload") or {}
        if not skill:
            return create_error_response(request, "INVALID_PARAMS", "skill is required")
        mode = p.get("mode") or "any"
        from_agent_id = p.get("from_agent_id")
        timeout = float(p.get("timeout") or 15.0)
        role = p.get("role")
        report = _run_async(send_to_skill(
            skill, payload,
            mode=mode,
            from_agent_id=from_agent_id,
            timeout=timeout,
            role=role,
        ))
        return create_success_response(request, {
            "summary": report.summary(),
            "succeeded": report.succeeded,
            "failed": report.failed,
            "per_agent": {aid: _outcome_to_dict(o) for aid, o in report.per_agent.items()},
            "targets": [_endpoint_to_dict(ep) for ep in report.targets],
        })
    except Exception as e:
        logger.error(f"[discovery] send_to_skill failed: {e}", exc_info=True)
        return create_error_response(request, "DISCOVERY_ERROR", str(e))
