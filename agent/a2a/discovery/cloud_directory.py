"""
Cloud directory client — AppSync-backed peer directory for WAN reach.

Pairs with the LAN zeroconf service. Every agent on this node is upserted
into AppSync's ``AgentEndpoint`` table with a 60 s heartbeat. The same client
subscribes to the org's change feed and to its own inbox(es), and feeds peer
endpoints into ``AgentDirectory`` so the router can pick LAN-direct vs
WAN-relay per call.

Graceful degradation: if the AppSync schema doesn't yet contain the Phase 2
types, every mutation/subscription will return a GraphQL error. We catch it,
log once, and let LAN discovery continue working. Re-enable automatically
once the schema is deployed (next heartbeat retry).
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional

import httpx

from agent.a2a.discovery.directory import AgentDirectory, get_directory
from agent.ec_tasks.appsync_pubsub import (
    AppSyncApiKeyConfig,
    _mk_http_headers,
    _post_graphql,
    _subscribe,
)
from utils.logger_helper import logger_helper as logger

HEARTBEAT_INTERVAL_SEC = 60.0
ENDPOINT_TTL_SEC = 180             # AppSync entry expiry; 3× heartbeat
INITIAL_QUERY_TIMEOUT_SEC = 10.0
SUBSCRIBE_MAX_IDLE_SEC = 600       # 10 min — keep WAN connection warm
SUBSCRIBE_MAX_RETRIES = 5


@dataclass
class AgentRegistration:
    """One agent we're advertising to the cloud directory."""
    agent_id: str
    machine_id: str
    name: str = ""
    role: str = ""
    skills: tuple[str, ...] = ()
    lan_host: Optional[str] = None
    lan_port: Optional[int] = None
    lan_path: str = "/a2a/"

    def relay_channel(self) -> str:
        # Channel == subscription filter value used by the recipient.
        return self.agent_id


# ---------- GraphQL templates ------------------------------------------------

def _gql_upsert_agent_endpoint() -> str:
    return """
    mutation UpsertAgentEndpoint($input: AgentEndpointInput!) {
      upsertAgentEndpoint(input: $input) {
        id machineId org name role skills a2aRelayChannel lanHint ttl
      }
    }
    """


def _gql_delete_agent_endpoint() -> str:
    return """
    mutation DeleteAgentEndpoint($id: ID!) {
      deleteAgentEndpoint(id: $id) { id }
    }
    """


def _gql_query_agent_endpoints() -> str:
    return """
    query QueryAgentEndpoints($org: String!) {
      queryAgentEndpoints(org: $org) {
        id machineId org name role skills a2aRelayChannel lanHint
      }
    }
    """


def _gql_sub_endpoint_changed() -> str:
    return """
    subscription OnAgentEndpointChanged($org: String!) {
      onAgentEndpointChanged(org: $org) {
        id machineId org name role skills a2aRelayChannel lanHint
      }
    }
    """


# ---------- helpers ----------------------------------------------------------

def _skills_to_csv(skills: tuple[str, ...]) -> str:
    return ",".join(s for s in skills if s)


def _csv_to_skills(s: Optional[str]) -> tuple[str, ...]:
    if not s:
        return ()
    return tuple(p for p in s.split(",") if p)


def _lan_hint_json(reg: AgentRegistration) -> Optional[str]:
    if not (reg.lan_host and reg.lan_port):
        return None
    try:
        return json.dumps(
            {"host": reg.lan_host, "port": int(reg.lan_port), "path": reg.lan_path or "/a2a/"}
        )
    except Exception:
        return None


def _parse_lan_hint(raw: Optional[str]) -> Optional[dict]:
    if not raw:
        return None
    try:
        d = json.loads(raw)
        if isinstance(d, dict) and d.get("host") and d.get("port"):
            return d
    except Exception:
        pass
    return None


# ---------- main client ------------------------------------------------------

class CloudDirectoryClient:
    """Per-process AppSync directory manager.

    One instance per eCan process; manages heartbeats for all local agents
    plus a single subscription per (org, inbox) feeding the AgentDirectory.
    """

    def __init__(
        self,
        *,
        config: AppSyncApiKeyConfig,
        org: str,
        machine_id: str,
        loop: asyncio.AbstractEventLoop,
        directory: Optional[AgentDirectory] = None,
    ) -> None:
        self._config = config
        self._org = org
        self._machine_id = machine_id
        self._loop = loop
        self._directory = directory or get_directory()

        self._registrations: Dict[str, AgentRegistration] = {}
        self._lock = threading.RLock()

        self._heartbeat_task: Optional[asyncio.Task] = None
        self._endpoint_sub_task: Optional[asyncio.Task] = None
        self._inbox_sub_tasks: Dict[str, asyncio.Task] = {}    # agent_id → task
        self._on_inbound_message: Optional[Callable[[str, dict], Awaitable[None]]] = None

        # Used to suppress repeated "schema not deployed" warnings.
        self._schema_warn_logged = False
        self._stopped = False

    def set_inbound_handler(self, fn: Callable[[str, dict], Awaitable[None]]) -> None:
        """Register the coroutine called when a WAN A2A message arrives for one
        of our local agents. ``fn(to_agent_id, payload_dict)``.
        """
        self._on_inbound_message = fn

    # ---- public API: agent registration -------------------------------------

    def set_local_agents(self, regs: List[AgentRegistration]) -> None:
        """Replace the set of local agents we advertise. Schedules upserts +
        subscription updates on the asyncio loop."""
        with self._lock:
            old_ids = set(self._registrations.keys())
            new_ids = {r.agent_id for r in regs}
            self._registrations = {r.agent_id: r for r in regs}

            # Stop subscriptions for removed agents
            for old_id in old_ids - new_ids:
                self._cancel_inbox_subscription(old_id)
                self._schedule(self._delete_endpoint(old_id))

            # Upsert all current
            for r in regs:
                self._schedule(self._upsert_endpoint(r))
                if r.agent_id not in self._inbox_sub_tasks:
                    self._start_inbox_subscription(r.agent_id)

    # ---- lifecycle -----------------------------------------------------------

    def start(self) -> None:
        """Start the org-wide endpoint subscription + heartbeat loop."""
        if self._stopped:
            return
        if self._endpoint_sub_task is None:
            self._endpoint_sub_task = self._schedule(self._endpoint_change_loop())
        if self._heartbeat_task is None:
            self._heartbeat_task = self._schedule(self._heartbeat_loop())
        # Also do an initial query so we don't have to wait for subscription
        # events to populate the directory.
        self._schedule(self._initial_query())
        logger.info(
            f"[discovery.cloud] CloudDirectoryClient started — org={self._org} "
            f"machine_id={self._machine_id[:8]}.. endpoint={self._config.http_endpoint}"
        )

    def stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        with self._lock:
            local_ids = list(self._registrations.keys())
        # Best-effort delete of our own endpoints so peers see us drop fast.
        for aid in local_ids:
            self._schedule(self._delete_endpoint(aid))
        # Cancel pumps
        for t in [self._heartbeat_task, self._endpoint_sub_task]:
            if t is not None:
                try:
                    t.cancel()
                except Exception:
                    pass
        for aid, t in list(self._inbox_sub_tasks.items()):
            try:
                t.cancel()
            except Exception:
                pass
        self._inbox_sub_tasks.clear()
        logger.info("[discovery.cloud] CloudDirectoryClient stopped")

    # ---- internals: scheduling ----------------------------------------------

    def _schedule(self, coro) -> asyncio.Task:
        """Schedule a coroutine on the bound loop, safely from any thread."""
        if self._loop.is_closed():
            class _Dummy:
                def cancel(self_inner):
                    pass
                def done(self_inner):
                    return True
            return _Dummy()  # type: ignore[return-value]
        if asyncio.get_event_loop_policy()._local._loop is self._loop:  # noqa: SLF001
            # Same loop — direct create_task
            return self._loop.create_task(coro)
        # Cross-thread — schedule and adapt to a Task-like
        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        class _FutAsTask:
            def cancel(self_inner):
                fut.cancel()
            def done(self_inner):
                return fut.done()
        return _FutAsTask()  # type: ignore[return-value]

    # ---- internals: mutations ----------------------------------------------

    async def _upsert_endpoint(self, reg: AgentRegistration) -> None:
        try:
            payload = {
                "input": {
                    "id": reg.agent_id,
                    "machineId": reg.machine_id,
                    "org": self._org,
                    "name": reg.name,
                    "role": reg.role,
                    "skills": _skills_to_csv(reg.skills),
                    "skillsHash": "",
                    "a2aRelayChannel": reg.relay_channel(),
                    "lanHint": _lan_hint_json(reg),
                    "ecanVer": "",
                    "os": "",
                    "ttl": ENDPOINT_TTL_SEC,
                }
            }
            await _post_graphql(
                self._config.http_endpoint,
                api_key=self._config.api_key,
                query=_gql_upsert_agent_endpoint(),
                variables=payload,
            )
            logger.debug(
                f"[discovery.cloud] upserted endpoint {reg.agent_id} (org={self._org})"
            )
        except Exception as e:
            self._maybe_warn_schema(e, op="upsertAgentEndpoint")

    async def _delete_endpoint(self, agent_id: str) -> None:
        try:
            await _post_graphql(
                self._config.http_endpoint,
                api_key=self._config.api_key,
                query=_gql_delete_agent_endpoint(),
                variables={"id": agent_id},
            )
            logger.debug(f"[discovery.cloud] deleted endpoint {agent_id}")
        except Exception as e:
            # Don't warn here — delete failures are common on shutdown.
            logger.debug(f"[discovery.cloud] delete endpoint {agent_id} failed: {e}")

    async def _initial_query(self) -> None:
        try:
            r = await _post_graphql(
                self._config.http_endpoint,
                api_key=self._config.api_key,
                query=_gql_query_agent_endpoints(),
                variables={"org": self._org},
            )
            items = (r.get("data") or {}).get("queryAgentEndpoints") or []
            for it in items:
                self._absorb_endpoint(it)
            logger.info(
                f"[discovery.cloud] initial query — found {len(items)} peer endpoint(s)"
            )
        except Exception as e:
            self._maybe_warn_schema(e, op="queryAgentEndpoints")

    # ---- internals: subscriptions ------------------------------------------

    async def _endpoint_change_loop(self) -> None:
        """Subscribe to onAgentEndpointChanged(org=self.org) and feed directory."""

        async def on_envelope(envelope: Dict[str, Any]) -> None:
            data = (envelope.get("payload") or {}).get("data") or {}
            ep = data.get("onAgentEndpointChanged")
            if not ep:
                return
            self._absorb_endpoint(ep)

        try:
            await _subscribe(
                config=self._config,
                query=_gql_sub_endpoint_changed(),
                variables={"org": self._org},
                operation_name="OnAgentEndpointChanged",
                field_name="onAgentEndpointChanged",
                on_envelope=on_envelope,
                max_retries=SUBSCRIBE_MAX_RETRIES,
                max_idle_sec=SUBSCRIBE_MAX_IDLE_SEC,
            )
        except asyncio.CancelledError:
            return
        except Exception as e:
            self._maybe_warn_schema(e, op="onAgentEndpointChanged")

    def _start_inbox_subscription(self, agent_id: str) -> None:
        """Subscribe to onA2AMessage(toAgentId=agent_id) so this local agent
        receives WAN-relayed messages."""
        if agent_id in self._inbox_sub_tasks:
            return

        from agent.a2a.discovery.wan_relay import subscribe_a2a_inbox

        async def runner():
            try:
                await subscribe_a2a_inbox(
                    config=self._config,
                    agent_id=agent_id,
                    on_message=self._dispatch_inbound,
                )
            except asyncio.CancelledError:
                return
            except Exception as e:
                self._maybe_warn_schema(e, op=f"onA2AMessage({agent_id})")

        self._inbox_sub_tasks[agent_id] = self._schedule(runner())  # type: ignore[assignment]
        logger.info(f"[discovery.cloud] inbox subscription started for {agent_id}")

    def _cancel_inbox_subscription(self, agent_id: str) -> None:
        t = self._inbox_sub_tasks.pop(agent_id, None)
        if t is not None:
            try:
                t.cancel()
            except Exception:
                pass
            logger.debug(f"[discovery.cloud] inbox subscription cancelled for {agent_id}")

    async def _dispatch_inbound(self, to_agent_id: str, payload: dict) -> None:
        """Route an incoming WAN A2A message into the local app's handler."""
        if self._on_inbound_message is None:
            logger.debug(
                f"[discovery.cloud] inbound A2A for {to_agent_id} dropped — "
                f"no handler registered"
            )
            return
        try:
            await self._on_inbound_message(to_agent_id, payload)
        except Exception as e:
            logger.warning(
                f"[discovery.cloud] inbound handler error for {to_agent_id}: {e}"
            )

    # ---- internals: heartbeat ----------------------------------------------

    async def _heartbeat_loop(self) -> None:
        while not self._stopped:
            try:
                await asyncio.sleep(HEARTBEAT_INTERVAL_SEC)
                if self._stopped:
                    return
                with self._lock:
                    regs = list(self._registrations.values())
                for r in regs:
                    await self._upsert_endpoint(r)
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.debug(f"[discovery.cloud] heartbeat error: {e}")

    # ---- internals: directory merge ----------------------------------------

    def _absorb_endpoint(self, ep: dict) -> None:
        """Push a remote endpoint record into AgentDirectory (skipping self)."""
        try:
            agent_id = ep.get("id") or ""
            machine_id = ep.get("machineId") or ""
            if not agent_id or not machine_id:
                return
            if machine_id == self._machine_id:
                return
            relay = ep.get("a2aRelayChannel") or agent_id
            self._directory.update_wan_agent(
                agent_id=agent_id,
                machine_id=machine_id,
                org=self._org,
                relay_channel=relay,
                name=ep.get("name") or "",
                role=ep.get("role") or "",
                skills=_csv_to_skills(ep.get("skills")),
                lan_hint=_parse_lan_hint(ep.get("lanHint")),
            )
            logger.info(
                f"[discovery.cloud] WAN endpoint up: agent_id={agent_id} "
                f"machine_id={machine_id[:8]}.. name='{ep.get('name')}'"
            )
        except Exception as e:
            logger.debug(f"[discovery.cloud] absorb failed: {e}")

    def _maybe_warn_schema(self, err: Exception, op: str) -> None:
        msg = str(err).lower()
        looks_like_missing_schema = (
            "unknown field" in msg
            or "cannot query field" in msg
            or "does not exist" in msg
            or "not defined" in msg
            or "no field" in msg
        )
        if looks_like_missing_schema and not self._schema_warn_logged:
            self._schema_warn_logged = True
            logger.warning(
                f"[discovery.cloud] '{op}' failed against AppSync — likely the "
                f"Phase 2 schema (AgentEndpoint / A2AMessage) hasn't been "
                f"deployed yet. WAN discovery + relay disabled until deployed. "
                f"Error: {err}"
            )
        else:
            logger.debug(f"[discovery.cloud] {op} error: {err}")


# Process singleton ---------------------------------------------------------

_client_instance: Optional[CloudDirectoryClient] = None
_client_lock = threading.Lock()


def start_cloud_directory(
    *,
    config: AppSyncApiKeyConfig,
    org: str,
    machine_id: str,
    loop: asyncio.AbstractEventLoop,
) -> Optional[CloudDirectoryClient]:
    """Start the singleton. Idempotent. Returns None on failure."""
    global _client_instance
    with _client_lock:
        if _client_instance is not None:
            return _client_instance
        try:
            c = CloudDirectoryClient(
                config=config, org=org, machine_id=machine_id, loop=loop
            )
            c.start()
            _client_instance = c
            return c
        except Exception as e:
            logger.warning(f"[discovery.cloud] start failed: {e}")
            return None


def stop_cloud_directory() -> None:
    global _client_instance
    with _client_lock:
        if _client_instance is None:
            return
        try:
            _client_instance.stop()
        except Exception as e:
            logger.debug(f"[discovery.cloud] stop error: {e}")
        _client_instance = None


def get_cloud_directory() -> Optional[CloudDirectoryClient]:
    return _client_instance
