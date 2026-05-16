"""
Unified in-process directory of known agents — LAN + (future) WAN.

Phase 1: populated only by the zeroconf listener. Phase 2 will add
``update_wan_endpoint`` populated by an AppSync subscription, and
``a2a_send`` will route through ``lookup()`` choosing LAN-direct when
reachable and WAN-relay otherwise.

Thread-safety: the directory is mutated from the zeroconf service browser
thread (an internal thread that python-zeroconf owns) and from the asyncio
loop (for the future Phase 2 AppSync subscription). We hold a single
``RLock`` around the dict — operations are O(1) so contention is negligible.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from utils.logger_helper import logger_helper as logger


@dataclass
class AgentEndpoint:
    """Where one agent can be reached.

    Filled in by the LAN listener (`lan_*` fields) and, in Phase 2, by the
    AppSync subscription (`wan_*` fields).
    """
    agent_id: str
    machine_id: str
    org: str
    name: str = ""
    role: str = ""
    skills: tuple[str, ...] = ()

    # LAN-direct reachability (from zeroconf)
    lan_host: Optional[str] = None     # e.g. "192.168.1.20" or hostname
    lan_port: Optional[int] = None     # the A2A listen port
    lan_path: str = "/a2a/"
    lan_last_seen: float = 0.0

    # WAN reachability via AppSync relay (Phase 2 — unpopulated for now)
    wan_relay_channel: Optional[str] = None
    wan_last_seen: float = 0.0

    # Sticky metadata
    auth_fp: str = ""
    raw_txt: dict = field(default_factory=dict)

    @property
    def lan_url(self) -> Optional[str]:
        if not (self.lan_host and self.lan_port):
            return None
        return f"http://{self.lan_host}:{self.lan_port}{self.lan_path}"

    @property
    def is_lan_reachable(self) -> bool:
        """Heuristic — has LAN endpoint and we saw it recently."""
        return bool(self.lan_url) and (time.time() - self.lan_last_seen) < 180


@dataclass
class NodeEndpoint:
    """One eCan instance (a physical machine running the app)."""
    machine_id: str
    org: str
    machine_name: str = ""
    role: str = ""
    os: str = ""
    arch: str = ""
    ecan_ver: str = ""
    agent_count: int = 0
    lan_host: Optional[str] = None
    api_port: Optional[int] = None
    lan_last_seen: float = 0.0
    auth_fp: str = ""
    raw_txt: dict = field(default_factory=dict)


class AgentDirectory:
    """Process-singleton directory of known agents and nodes.

    Use ``get_directory()`` to access — don't construct directly.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._agents: Dict[str, AgentEndpoint] = {}
        self._nodes: Dict[str, NodeEndpoint] = {}
        # Self-machine id so we can filter our own advertisements out of
        # results passed back to callers (avoids loop-of-one A2A calls).
        self._self_machine_id: Optional[str] = None

    # ---- self identification ------------------------------------------------

    def set_self_machine_id(self, machine_id: str) -> None:
        with self._lock:
            self._self_machine_id = machine_id

    # ---- mutation from LAN listener ----------------------------------------

    def update_lan_agent(
        self,
        *,
        agent_id: str,
        machine_id: str,
        org: str,
        host: str,
        port: int,
        path: str = "/a2a/",
        name: str = "",
        role: str = "",
        skills: tuple[str, ...] = (),
        auth_fp: str = "",
        raw_txt: Optional[dict] = None,
    ) -> None:
        with self._lock:
            ep = self._agents.get(agent_id)
            if ep is None:
                ep = AgentEndpoint(
                    agent_id=agent_id, machine_id=machine_id, org=org
                )
                self._agents[agent_id] = ep
            ep.machine_id = machine_id
            ep.org = org
            if name:
                ep.name = name
            if role:
                ep.role = role
            if skills:
                ep.skills = tuple(skills)
            ep.lan_host = host
            ep.lan_port = port
            ep.lan_path = path or "/a2a/"
            ep.lan_last_seen = time.time()
            ep.auth_fp = auth_fp
            if raw_txt is not None:
                ep.raw_txt = raw_txt

    def remove_lan_agent(self, agent_id: str) -> None:
        with self._lock:
            ep = self._agents.get(agent_id)
            if ep is None:
                return
            ep.lan_host = None
            ep.lan_port = None
            ep.lan_last_seen = 0.0
            # Don't pop — Phase 2 may still have a WAN route to this agent.
            # If both lan_* and wan_* are unset we GC at lookup time.

    def update_lan_node(
        self,
        *,
        machine_id: str,
        org: str,
        host: str,
        machine_name: str = "",
        role: str = "",
        os_name: str = "",
        arch: str = "",
        ecan_ver: str = "",
        agent_count: int = 0,
        api_port: Optional[int] = None,
        auth_fp: str = "",
        raw_txt: Optional[dict] = None,
    ) -> None:
        with self._lock:
            n = self._nodes.get(machine_id)
            if n is None:
                n = NodeEndpoint(machine_id=machine_id, org=org)
                self._nodes[machine_id] = n
            n.org = org
            n.lan_host = host
            if machine_name:
                n.machine_name = machine_name
            if role:
                n.role = role
            if os_name:
                n.os = os_name
            if arch:
                n.arch = arch
            if ecan_ver:
                n.ecan_ver = ecan_ver
            if agent_count:
                n.agent_count = agent_count
            if api_port is not None:
                n.api_port = api_port
            n.lan_last_seen = time.time()
            n.auth_fp = auth_fp
            if raw_txt is not None:
                n.raw_txt = raw_txt

    def remove_lan_node(self, machine_id: str) -> None:
        with self._lock:
            n = self._nodes.pop(machine_id, None)
            if n is None:
                return
            logger.debug(f"[discovery.directory] LAN node removed: {machine_id}")

    # ---- mutation from WAN (AppSync cloud directory) ------------------------

    def update_wan_agent(
        self,
        *,
        agent_id: str,
        machine_id: str,
        org: str,
        relay_channel: str,
        name: str = "",
        role: str = "",
        skills: tuple[str, ...] = (),
        lan_hint: Optional[dict] = None,
    ) -> None:
        """Record a WAN-reachable agent from the cloud directory.

        ``lan_hint`` is the peer's self-reported LAN endpoint (``{host, port,
        path}``) — useful when two nodes happen to be on the same LAN but
        zeroconf was blocked. The router probes it opportunistically.
        """
        with self._lock:
            ep = self._agents.get(agent_id)
            if ep is None:
                ep = AgentEndpoint(
                    agent_id=agent_id, machine_id=machine_id, org=org
                )
                self._agents[agent_id] = ep
            ep.machine_id = machine_id
            ep.org = org
            if name:
                ep.name = name
            if role:
                ep.role = role
            if skills:
                ep.skills = tuple(skills)
            ep.wan_relay_channel = relay_channel
            ep.wan_last_seen = time.time()
            # If the cloud hint gives us a LAN endpoint we don't already
            # know about, record it as a fallback so the router can probe.
            if lan_hint and not ep.lan_host:
                host = (lan_hint.get("host") or "").strip()
                port = lan_hint.get("port")
                if host and port:
                    try:
                        ep.lan_host = host
                        ep.lan_port = int(port)
                        ep.lan_path = lan_hint.get("path") or "/a2a/"
                        # NOTE: we DON'T bump lan_last_seen — that's reserved
                        # for actual zeroconf observation. A cloud hint is
                        # just a candidate to probe.
                    except (TypeError, ValueError):
                        pass

    def remove_wan_agent(self, agent_id: str) -> None:
        with self._lock:
            ep = self._agents.get(agent_id)
            if ep is None:
                return
            ep.wan_relay_channel = None
            ep.wan_last_seen = 0.0
            # Same GC-on-lookup policy as LAN removal.

    # ---- read-side ----------------------------------------------------------

    def lookup(self, agent_id: str) -> Optional[AgentEndpoint]:
        with self._lock:
            ep = self._agents.get(agent_id)
            if ep is None:
                return None
            # GC entries that have neither LAN nor WAN routes.
            if not ep.lan_url and not ep.wan_relay_channel:
                self._agents.pop(agent_id, None)
                return None
            return ep

    def list_agents(self, *, exclude_self: bool = True) -> List[AgentEndpoint]:
        with self._lock:
            self_mid = self._self_machine_id if exclude_self else None
            out: List[AgentEndpoint] = []
            for ep in self._agents.values():
                if self_mid and ep.machine_id == self_mid:
                    continue
                out.append(ep)
            return out

    def list_nodes(self, *, exclude_self: bool = True) -> List[NodeEndpoint]:
        with self._lock:
            self_mid = self._self_machine_id if exclude_self else None
            return [
                n for n in self._nodes.values()
                if not (self_mid and n.machine_id == self_mid)
            ]

    def snapshot(self) -> dict:
        """For debug / IPC handlers — returns a JSON-safe summary."""
        with self._lock:
            return {
                "self_machine_id": self._self_machine_id,
                "nodes": [
                    {
                        "machine_id": n.machine_id,
                        "machine_name": n.machine_name,
                        "host": n.lan_host,
                        "role": n.role,
                        "os": n.os,
                        "ecan_ver": n.ecan_ver,
                        "agent_count": n.agent_count,
                        "last_seen": n.lan_last_seen,
                    }
                    for n in self._nodes.values()
                ],
                "agents": [
                    {
                        "agent_id": a.agent_id,
                        "machine_id": a.machine_id,
                        "name": a.name,
                        "role": a.role,
                        "skills": list(a.skills),
                        "lan_url": a.lan_url,
                        "wan_channel": a.wan_relay_channel,
                        "last_seen_lan": a.lan_last_seen,
                        "last_seen_wan": a.wan_last_seen,
                    }
                    for a in self._agents.values()
                ],
            }


_directory_instance: Optional[AgentDirectory] = None
_directory_lock = threading.Lock()


def get_directory() -> AgentDirectory:
    """Process-singleton accessor."""
    global _directory_instance
    if _directory_instance is None:
        with _directory_lock:
            if _directory_instance is None:
                _directory_instance = AgentDirectory()
    return _directory_instance
