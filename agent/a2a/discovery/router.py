"""
Unified A2A send — picks LAN-direct vs WAN-relay per call.

This is the Phase 2 headline feature. Callers say "send this payload to
agent X" and the router consults ``AgentDirectory`` to pick the cheapest
working transport:

    1. Same machine? → handled by the existing in-process MCP path (we
       don't intercept those — callers should already use direct dispatch).
    2. Same LAN, agent advertised via zeroconf AND reachable on a recent
       probe? → HTTP POST to the agent's a2a URL (fast, no cloud round trip).
    3. WAN-only (cloud-registered) OR LAN probe failed? → publish via
       AppSync ``sendA2AMessage`` mutation; the recipient's subscription
       picks it up and feeds it into its local A2A handler.

Existing eCan callers that pass hardcoded URLs (``a2a_send -> Mary B @
http://192.168.10.100:3602``) continue to work unchanged. Migrate them to
``send_to_agent(agent_id, payload)`` when convenient — that's when they
gain WAN reachability.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from dataclasses import dataclass
from typing import Optional, Tuple

import httpx

from agent.a2a.discovery.directory import AgentDirectory, AgentEndpoint, get_directory
from agent.ec_tasks.appsync_pubsub import AppSyncApiKeyConfig
from utils.logger_helper import logger_helper as logger

LAN_PROBE_TIMEOUT_SEC = 1.5
LAN_PROBE_CACHE_TTL_SEC = 30.0
SEND_DEFAULT_TIMEOUT_SEC = 15.0


@dataclass
class _LanProbeCacheEntry:
    reachable: bool
    last_checked: float


# Singleton-ish module state — the router has no per-instance state to track
# besides the LAN probe cache and the cloud config (set by the bootstrap).
_lan_probe_cache: dict[str, _LanProbeCacheEntry] = {}
_lan_probe_lock = threading.Lock()

_cloud_config: Optional[AppSyncApiKeyConfig] = None
_org: Optional[str] = None
_self_agent_id_default: Optional[str] = None


def configure_router(
    *,
    cloud_config: Optional[AppSyncApiKeyConfig],
    org: str,
    self_agent_id_default: Optional[str] = None,
) -> None:
    """One-time configuration. Safe to call again to update."""
    global _cloud_config, _org, _self_agent_id_default
    _cloud_config = cloud_config
    _org = org
    _self_agent_id_default = self_agent_id_default
    logger.info(
        f"[discovery.router] configured — org={org} "
        f"cloud_relay={'on' if cloud_config else 'off'}"
    )


class SendResult:
    LAN = "lan"
    WAN = "wan"
    UNREACHABLE = "unreachable"


@dataclass
class SendOutcome:
    transport: str
    success: bool
    error: Optional[str] = None
    response: Optional[dict] = None


async def send_to_agent(
    agent_id: str,
    payload: dict,
    *,
    from_agent_id: Optional[str] = None,
    timeout: float = SEND_DEFAULT_TIMEOUT_SEC,
    directory: Optional[AgentDirectory] = None,
) -> SendOutcome:
    """Route a JSON payload to ``agent_id``, picking the best transport.

    ``payload`` is the A2A JSON-RPC envelope (whatever the existing
    ``A2AClientWrapper`` would send). Returns a ``SendOutcome`` describing
    which transport was used and whether it succeeded.
    """
    d = directory or get_directory()
    ep = d.lookup(agent_id)
    if ep is None:
        return SendOutcome(SendResult.UNREACHABLE, False, error="agent unknown")

    sender = from_agent_id or _self_agent_id_default or "unknown"

    # Try LAN first if endpoint advertises one and we don't have a recent
    # "unreachable" cache entry.
    if ep.lan_url and _lan_recently_reachable(ep.lan_url):
        try:
            resp = await _post_lan(ep.lan_url, payload, timeout)
            _cache_lan_probe(ep.lan_url, True)
            return SendOutcome(SendResult.LAN, True, response=resp)
        except (httpx.ConnectError, httpx.TimeoutException, asyncio.TimeoutError) as e:
            _cache_lan_probe(ep.lan_url, False)
            logger.info(
                f"[discovery.router] LAN to {agent_id} ({ep.lan_url}) failed: {e}; "
                f"falling back to WAN"
            )
        except Exception as e:
            _cache_lan_probe(ep.lan_url, False)
            logger.warning(
                f"[discovery.router] LAN to {agent_id} ({ep.lan_url}) errored: {e}; "
                f"falling back to WAN"
            )

    # WAN fallback
    if ep.wan_relay_channel and _cloud_config is not None and _org:
        from agent.a2a.discovery.wan_relay import send_via_wan
        ok = await send_via_wan(
            config=_cloud_config,
            to_agent_id=agent_id,
            from_agent_id=sender,
            org=_org,
            payload=payload,
            timeout=timeout,
        )
        return SendOutcome(SendResult.WAN if ok else SendResult.UNREACHABLE, ok,
                           error=None if ok else "wan publish failed")

    return SendOutcome(
        SendResult.UNREACHABLE,
        False,
        error="no LAN endpoint reachable and no WAN relay channel/cloud config",
    )


# ---- internals --------------------------------------------------------------

async def _post_lan(url: str, payload: dict, timeout: float) -> dict:
    """HTTP POST a JSON payload to a LAN A2A endpoint and return the parsed reply."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        try:
            return resp.json()
        except Exception:
            return {"_raw_text": resp.text}


def _lan_recently_reachable(url: str) -> bool:
    """Decide if we should attempt the LAN url based on cached probe outcomes."""
    with _lan_probe_lock:
        entry = _lan_probe_cache.get(url)
        if entry is None:
            return True   # unknown → optimistic, try once
        age = time.time() - entry.last_checked
        if age > LAN_PROBE_CACHE_TTL_SEC:
            return True   # cache stale → re-probe
        return entry.reachable


def _cache_lan_probe(url: str, reachable: bool) -> None:
    with _lan_probe_lock:
        _lan_probe_cache[url] = _LanProbeCacheEntry(
            reachable=reachable, last_checked=time.time()
        )


# ---- introspection helpers (used by IPC/handlers/UI) -----------------------

def list_known_agents(
    *, exclude_self: bool = True, directory: Optional[AgentDirectory] = None
) -> list[AgentEndpoint]:
    """Return all agents the router could potentially send to (LAN ∪ WAN)."""
    return (directory or get_directory()).list_agents(exclude_self=exclude_self)


def transport_for(agent_id: str, *, directory: Optional[AgentDirectory] = None) -> str:
    """Best-effort summary of the transport that would be used. Doesn't probe.

    Returns one of: "lan", "wan", "lan+wan", "none".
    """
    ep = (directory or get_directory()).lookup(agent_id)
    if ep is None:
        return "none"
    has_lan = bool(ep.lan_url)
    has_wan = bool(ep.wan_relay_channel) and (_cloud_config is not None)
    if has_lan and has_wan:
        return "lan+wan"
    if has_lan:
        return "lan"
    if has_wan:
        return "wan"
    return "none"
