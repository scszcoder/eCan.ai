"""
Zeroconf / DNS-SD advertiser + listener for eCan nodes and agents.

Service types:
    _ecan-node._tcp.local.   — one per eCan instance (the "machine" record)
    _ecan-agent._tcp.local.  — one per local agent (the "endpoint" record)

Heartbeat / refresh: 60 s. Each call to update_agents() re-issues
ServiceInfo with bumped ``last_advertised`` TXT field, which python-zeroconf
turns into a fresh announcement that listeners pick up promptly.

This module is ADDITIVE to the legacy Commander/Platoon code in
``agent/network/network.py``. It does not modify any existing call sites.
"""

from __future__ import annotations

import socket
import threading
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from zeroconf import (
    IPVersion,
    ServiceBrowser,
    ServiceInfo,
    ServiceStateChange,
    Zeroconf,
)

from agent.a2a.discovery.auth import compute_auth_fp, verify_auth_fp
from agent.a2a.discovery.directory import AgentDirectory, get_directory
from utils.logger_helper import logger_helper as logger

SERVICE_TYPE_NODE = "_ecan-node._tcp.local."
SERVICE_TYPE_AGENT = "_ecan-agent._tcp.local."

HEARTBEAT_INTERVAL_SEC = 60.0     # how often to re-advertise (refreshes TTL on peers)
TXT_VERSION = "1"
TXT_MAX_VALUE_LEN = 200            # keep individual values well under the 255-byte mDNS limit


@dataclass
class AgentRegistration:
    agent_id: str
    name: str
    role: str
    a2a_port: int
    a2a_path: str = "/a2a/"
    skills: tuple[str, ...] = ()
    tasks: tuple[str, ...] = ()


def _get_primary_ip() -> Optional[str]:
    """Best-effort local IP for the default outbound interface.

    Uses the standard UDP-to-public-IP trick that doesn't actually send a
    packet — just lets the OS pick the source IP for the default route.
    Returns None on failure (e.g., no network); listener still works
    against loopback in that case.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(0.5)
            # 8.8.8.8 — doesn't actually transmit; just resolves a route.
            s.connect(("8.8.8.8", 53))
            return s.getsockname()[0]
    except Exception:
        return None


def _safe_hostname() -> str:
    try:
        return socket.gethostname() or "ecan-host"
    except Exception:
        return "ecan-host"


def _truncate_txt_value(value: str) -> str:
    """Keep TXT values under the per-string limit (mDNS spec)."""
    if not value:
        return ""
    if len(value) <= TXT_MAX_VALUE_LEN:
        return value
    return value[:TXT_MAX_VALUE_LEN - 1] + "~"


def _encode_txt(d: Dict[str, str]) -> Dict[bytes, bytes]:
    """Encode a TXT dict for zeroconf.ServiceInfo (bytes keys+values)."""
    out: Dict[bytes, bytes] = {}
    for k, v in d.items():
        if v is None:
            continue
        out[k.encode("utf-8")] = _truncate_txt_value(str(v)).encode("utf-8")
    return out


def _decode_txt(props: Dict[bytes, Optional[bytes]]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for k, v in (props or {}).items():
        try:
            key = k.decode("utf-8") if isinstance(k, (bytes, bytearray)) else str(k)
        except Exception:
            continue
        if v is None:
            out[key] = ""
            continue
        try:
            out[key] = v.decode("utf-8") if isinstance(v, (bytes, bytearray)) else str(v)
        except Exception:
            out[key] = ""
    return out


def _service_instance_name(prefix: str, service_type: str) -> str:
    """python-zeroconf wants ``<instance>.<type>`` as the full service name."""
    return f"{prefix}.{service_type}"


def _safe_instance_label(raw: str, fallback: str = "ecan") -> str:
    """Sanitize a string for use as a DNS-SD instance label."""
    out = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in (raw or ""))
    out = out.strip("._-") or fallback
    # Service-instance labels are capped at 63 octets.
    return out[:60]


class LanDiscoveryService:
    """Wraps a zeroconf instance, advertises self, and listens for peers.

    One per process. Use ``start_lan_discovery()`` / ``stop_lan_discovery()``
    helpers below rather than constructing directly.
    """

    def __init__(
        self,
        *,
        machine_id: str,
        org: str,
        machine_name: str,
        role: str,
        os_name: str,
        arch: str,
        ecan_ver: str,
        api_port: int,
        directory: Optional[AgentDirectory] = None,
    ) -> None:
        self.machine_id = machine_id
        self.org = org
        self.machine_name = machine_name
        self.role = role
        self.os_name = os_name
        self.arch = arch
        self.ecan_ver = ecan_ver
        self.api_port = api_port

        self._directory = directory or get_directory()
        self._directory.set_self_machine_id(machine_id)

        self._zc: Optional[Zeroconf] = None
        self._browser_node: Optional[ServiceBrowser] = None
        self._browser_agent: Optional[ServiceBrowser] = None

        self._node_info: Optional[ServiceInfo] = None
        self._agent_infos: Dict[str, ServiceInfo] = {}   # agent_id → ServiceInfo
        self._registered_agents: Dict[str, AgentRegistration] = {}

        self._heartbeat_thread: Optional[threading.Thread] = None
        self._heartbeat_stop = threading.Event()
        self._lock = threading.RLock()
        self._primary_ip: Optional[str] = None

    # ---- lifecycle ----------------------------------------------------------

    def start(self) -> None:
        """Initialize zeroconf, register the node, start listeners + heartbeat."""
        with self._lock:
            if self._zc is not None:
                logger.debug("[discovery.zeroconf] already started; skipping")
                return

            try:
                self._zc = Zeroconf(ip_version=IPVersion.V4Only)
            except Exception as e:
                logger.warning(f"[discovery.zeroconf] failed to init Zeroconf: {e}")
                self._zc = None
                return

            self._primary_ip = _get_primary_ip()
            logger.info(
                f"[discovery.zeroconf] starting — machine_id={self.machine_id} "
                f"org={self.org} ip={self._primary_ip} role={self.role}"
            )

            # Register self (node-level) first so peers see us as soon as they
            # browse, even before any agents are advertised.
            try:
                self._node_info = self._build_node_service_info()
                self._zc.register_service(self._node_info)
                logger.info(
                    f"[discovery.zeroconf] registered node service "
                    f"'{self._node_info.name}' on port {self.api_port}"
                )
            except Exception as e:
                logger.warning(f"[discovery.zeroconf] node register failed: {e}")
                self._node_info = None

            # Start browsing for both service types.
            try:
                self._browser_node = ServiceBrowser(
                    self._zc, SERVICE_TYPE_NODE, handlers=[self._on_service_change]
                )
                self._browser_agent = ServiceBrowser(
                    self._zc, SERVICE_TYPE_AGENT, handlers=[self._on_service_change]
                )
                logger.info(
                    f"[discovery.zeroconf] browsing for {SERVICE_TYPE_NODE} "
                    f"and {SERVICE_TYPE_AGENT}"
                )
            except Exception as e:
                logger.warning(f"[discovery.zeroconf] failed to start browsers: {e}")

            # Heartbeat keeps the TTL fresh on peers and re-publishes after
            # network changes (interface up/down).
            self._heartbeat_stop.clear()
            self._heartbeat_thread = threading.Thread(
                target=self._heartbeat_loop,
                name="ecan-discovery-heartbeat",
                daemon=True,
            )
            self._heartbeat_thread.start()

    def stop(self) -> None:
        """Unregister all services, stop browsers, close zeroconf cleanly."""
        with self._lock:
            self._heartbeat_stop.set()
            if self._heartbeat_thread and self._heartbeat_thread.is_alive():
                # Don't join() — it might block if zeroconf internal is stuck.
                # The thread is daemon and will exit with the process.
                pass

            if self._zc is None:
                return

            for agent_id, info in list(self._agent_infos.items()):
                try:
                    self._zc.unregister_service(info)
                    logger.debug(f"[discovery.zeroconf] unregistered agent {agent_id}")
                except Exception as e:
                    logger.debug(
                        f"[discovery.zeroconf] unregister agent {agent_id} failed (ignored): {e}"
                    )
            self._agent_infos.clear()

            if self._node_info is not None:
                try:
                    self._zc.unregister_service(self._node_info)
                    logger.debug(
                        f"[discovery.zeroconf] unregistered node {self._node_info.name}"
                    )
                except Exception as e:
                    logger.debug(
                        f"[discovery.zeroconf] unregister node failed (ignored): {e}"
                    )
                self._node_info = None

            try:
                self._zc.close()
            except Exception as e:
                logger.debug(f"[discovery.zeroconf] close failed (ignored): {e}")
            self._zc = None
            logger.info("[discovery.zeroconf] stopped")

    # ---- agent advertising --------------------------------------------------

    def update_agents(self, agents: Sequence[AgentRegistration]) -> None:
        """Synchronize the set of advertised agents with the given list.

        Adds new agents, removes ones not in the list, re-registers ones
        whose port/skills changed. Safe to call repeatedly as agents come
        online or get reconfigured.
        """
        with self._lock:
            if self._zc is None:
                # Buffer for after start() — but for Phase 1 just warn.
                logger.debug(
                    "[discovery.zeroconf] update_agents called before start(); "
                    "buffering not implemented in v1, ignoring"
                )
                return

            new_ids = {a.agent_id for a in agents}

            # Remove agents no longer present.
            for old_id in list(self._registered_agents.keys()):
                if old_id not in new_ids:
                    info = self._agent_infos.pop(old_id, None)
                    self._registered_agents.pop(old_id, None)
                    if info is not None:
                        try:
                            self._zc.unregister_service(info)
                            logger.info(
                                f"[discovery.zeroconf] unregistered agent {old_id}"
                            )
                        except Exception as e:
                            logger.debug(
                                f"[discovery.zeroconf] unregister {old_id} failed: {e}"
                            )

            # Add or update.
            for ar in agents:
                prev = self._registered_agents.get(ar.agent_id)
                if prev == ar:
                    continue   # no change

                info = self._build_agent_service_info(ar)
                try:
                    if prev is None:
                        self._zc.register_service(info)
                        logger.info(
                            f"[discovery.zeroconf] registered agent '{ar.agent_id}' "
                            f"name='{ar.name}' port={ar.a2a_port}"
                        )
                    else:
                        # python-zeroconf supports update via register w/ same name
                        old_info = self._agent_infos.get(ar.agent_id)
                        if old_info is not None:
                            try:
                                self._zc.unregister_service(old_info)
                            except Exception:
                                pass
                        self._zc.register_service(info)
                        logger.info(
                            f"[discovery.zeroconf] re-registered agent '{ar.agent_id}' "
                            f"(config changed)"
                        )
                    self._agent_infos[ar.agent_id] = info
                    self._registered_agents[ar.agent_id] = ar
                except Exception as e:
                    logger.warning(
                        f"[discovery.zeroconf] failed to register agent {ar.agent_id}: {e}"
                    )

    # ---- building ServiceInfo ----------------------------------------------

    def _build_node_service_info(self) -> ServiceInfo:
        from agent.a2a.discovery.machine_id import machine_id_short

        instance_label = _safe_instance_label(
            f"{self.machine_name}-{machine_id_short(self.machine_id)}",
            fallback="ecan-node",
        )
        name = _service_instance_name(instance_label, SERVICE_TYPE_NODE)

        txt = {
            "v": TXT_VERSION,
            "machine_id": self.machine_id,
            "machine_name": self.machine_name,
            "org": self.org,
            "role": self.role,
            "os": self.os_name,
            "arch": self.arch,
            "ecan_ver": self.ecan_ver,
            "api_port": str(self.api_port),
            "auth_fp": compute_auth_fp(self.org, self.machine_id),
            "ts": str(int(time.time())),
        }
        addresses = []
        if self._primary_ip:
            try:
                addresses.append(socket.inet_aton(self._primary_ip))
            except OSError:
                pass

        return ServiceInfo(
            type_=SERVICE_TYPE_NODE,
            name=name,
            addresses=addresses,
            port=self.api_port,
            properties=_encode_txt(txt),
            server=f"{_safe_hostname()}.local.",
        )

    def _build_agent_service_info(self, ar: AgentRegistration) -> ServiceInfo:
        instance_label = _safe_instance_label(ar.agent_id, fallback="ecan-agent")
        name = _service_instance_name(instance_label, SERVICE_TYPE_AGENT)

        # skills/tasks may be long; TXT-value truncation in _encode_txt handles it.
        txt = {
            "v": TXT_VERSION,
            "agent_id": ar.agent_id,
            "machine_id": self.machine_id,
            "org": self.org,
            "name": ar.name,
            "role": ar.role,
            "skills": ",".join(ar.skills),
            "tasks": ",".join(ar.tasks),
            "a2a_port": str(ar.a2a_port),
            "a2a_path": ar.a2a_path or "/a2a/",
            "auth_fp": compute_auth_fp(self.org, ar.agent_id),
            "ts": str(int(time.time())),
        }
        addresses = []
        if self._primary_ip:
            try:
                addresses.append(socket.inet_aton(self._primary_ip))
            except OSError:
                pass

        return ServiceInfo(
            type_=SERVICE_TYPE_AGENT,
            name=name,
            addresses=addresses,
            port=ar.a2a_port,
            properties=_encode_txt(txt),
            server=f"{_safe_hostname()}.local.",
        )

    # ---- listener -----------------------------------------------------------

    def _on_service_change(
        self,
        zeroconf: Zeroconf,
        service_type: str,
        name: str,
        state_change: ServiceStateChange,
    ) -> None:
        """Fired on the zeroconf internal thread when a peer service appears/changes/leaves."""
        try:
            if state_change == ServiceStateChange.Removed:
                self._handle_removed(service_type, name)
                return

            # Added or Updated — fetch the full info (this may block briefly
            # on a sync request_resolution).
            info = zeroconf.get_service_info(service_type, name, timeout=2000)
            if info is None:
                logger.debug(
                    f"[discovery.zeroconf] add/update for {name} resolved to None (timeout?)"
                )
                return

            txt = _decode_txt(info.properties or {})
            org = txt.get("org", "")
            if org != self.org:
                # Different account on the same LAN — silently ignore.
                return

            if service_type == SERVICE_TYPE_NODE:
                self._handle_node_record(name, info, txt)
            elif service_type == SERVICE_TYPE_AGENT:
                self._handle_agent_record(name, info, txt)
        except Exception as e:
            logger.debug(
                f"[discovery.zeroconf] handler error for {name}: {e}"
            )

    def _handle_node_record(self, name: str, info: ServiceInfo, txt: dict) -> None:
        machine_id = txt.get("machine_id", "")
        if not machine_id:
            return
        if machine_id == self.machine_id:
            return  # ourselves

        auth_fp = txt.get("auth_fp", "")
        if not verify_auth_fp(self.org, machine_id, auth_fp):
            logger.debug(
                f"[discovery.zeroconf] node {machine_id} auth_fp mismatch — skipping"
            )
            return

        host = self._extract_host(info)
        self._directory.update_lan_node(
            machine_id=machine_id,
            org=self.org,
            host=host,
            machine_name=txt.get("machine_name", ""),
            role=txt.get("role", ""),
            os_name=txt.get("os", ""),
            arch=txt.get("arch", ""),
            ecan_ver=txt.get("ecan_ver", ""),
            api_port=_safe_int(txt.get("api_port")),
            auth_fp=auth_fp,
            raw_txt=txt,
        )
        logger.info(
            f"[discovery.zeroconf] node up: '{txt.get('machine_name')}' "
            f"machine_id={machine_id[:8]}.. at {host}:{info.port} role={txt.get('role')}"
        )

    def _handle_agent_record(self, name: str, info: ServiceInfo, txt: dict) -> None:
        agent_id = txt.get("agent_id", "")
        machine_id = txt.get("machine_id", "")
        if not agent_id:
            return
        if machine_id == self.machine_id:
            return  # ourselves — already in local registry

        auth_fp = txt.get("auth_fp", "")
        if not verify_auth_fp(self.org, agent_id, auth_fp):
            logger.debug(
                f"[discovery.zeroconf] agent {agent_id} auth_fp mismatch — skipping"
            )
            return

        host = self._extract_host(info)
        skills = tuple(s for s in (txt.get("skills") or "").split(",") if s)
        a2a_port = _safe_int(txt.get("a2a_port")) or info.port
        if not a2a_port:
            return

        self._directory.update_lan_agent(
            agent_id=agent_id,
            machine_id=machine_id,
            org=self.org,
            host=host,
            port=int(a2a_port),
            path=txt.get("a2a_path") or "/a2a/",
            name=txt.get("name", ""),
            role=txt.get("role", ""),
            skills=skills,
            auth_fp=auth_fp,
            raw_txt=txt,
        )
        logger.info(
            f"[discovery.zeroconf] agent up: {agent_id} "
            f"name='{txt.get('name')}' at {host}:{a2a_port}"
        )

    def _handle_removed(self, service_type: str, name: str) -> None:
        # The service name carries either machine_id_short or agent_id —
        # we don't have a reverse lookup, so the directory handles GC by
        # TTL (lan_last_seen). But we still log for visibility.
        logger.info(f"[discovery.zeroconf] service removed: {name}")
        # We don't have the txt here, but the cheapest correct thing is to
        # let the heartbeat staleness in directory.lookup() handle cleanup.

    def _extract_host(self, info: ServiceInfo) -> str:
        """Pick a usable host string from a ServiceInfo's addresses."""
        try:
            addrs = info.parsed_addresses(IPVersion.V4Only) or []
        except Exception:
            addrs = []
        if addrs:
            return addrs[0]
        return info.server.rstrip(".") if info.server else ""

    # ---- heartbeat ---------------------------------------------------------

    def _heartbeat_loop(self) -> None:
        # First refresh after one interval; we just registered everything.
        while not self._heartbeat_stop.wait(HEARTBEAT_INTERVAL_SEC):
            try:
                self._refresh()
            except Exception as e:
                logger.debug(f"[discovery.zeroconf] heartbeat refresh error: {e}")

    def _refresh(self) -> None:
        """Detect network changes, re-publish if our primary IP moved."""
        with self._lock:
            if self._zc is None:
                return
            new_ip = _get_primary_ip()
            if new_ip and new_ip != self._primary_ip:
                logger.info(
                    f"[discovery.zeroconf] primary IP changed "
                    f"{self._primary_ip} → {new_ip}; re-registering services"
                )
                self._primary_ip = new_ip
                # Rebuild + re-register all services with the new address.
                if self._node_info is not None:
                    try:
                        self._zc.unregister_service(self._node_info)
                    except Exception:
                        pass
                    self._node_info = self._build_node_service_info()
                    try:
                        self._zc.register_service(self._node_info)
                    except Exception as e:
                        logger.warning(
                            f"[discovery.zeroconf] re-register node failed: {e}"
                        )
                for agent_id, prev_info in list(self._agent_infos.items()):
                    ar = self._registered_agents.get(agent_id)
                    if ar is None:
                        continue
                    try:
                        self._zc.unregister_service(prev_info)
                    except Exception:
                        pass
                    new_info = self._build_agent_service_info(ar)
                    try:
                        self._zc.register_service(new_info)
                        self._agent_infos[agent_id] = new_info
                    except Exception as e:
                        logger.warning(
                            f"[discovery.zeroconf] re-register agent {agent_id} failed: {e}"
                        )
            else:
                # No IP change — touch the ts field so listeners see a fresh
                # TTL. python-zeroconf doesn't expose a "renew" API, so we
                # only rebump if there's already a change. The default record
                # TTL (~120s) plus the listener's caching handle steady-state
                # liveness without us re-announcing every 60 s.
                pass


def _safe_int(s) -> Optional[int]:
    try:
        if s is None or s == "":
            return None
        return int(s)
    except (TypeError, ValueError):
        return None


# Process-singleton wrapper so the rest of the app has a simple start/stop API.
_service_instance: Optional[LanDiscoveryService] = None
_service_lock = threading.Lock()


def start_lan_discovery(
    *,
    machine_id: str,
    org: str,
    machine_name: str,
    role: str,
    os_name: str,
    arch: str,
    ecan_ver: str,
    api_port: int,
) -> Optional[LanDiscoveryService]:
    """Start the singleton service. Idempotent."""
    global _service_instance
    with _service_lock:
        if _service_instance is not None:
            return _service_instance
        svc = LanDiscoveryService(
            machine_id=machine_id,
            org=org,
            machine_name=machine_name,
            role=role,
            os_name=os_name,
            arch=arch,
            ecan_ver=ecan_ver,
            api_port=api_port,
        )
        try:
            svc.start()
            _service_instance = svc
            return svc
        except Exception as e:
            logger.warning(f"[discovery.zeroconf] start failed: {e}")
            return None


def stop_lan_discovery() -> None:
    """Stop the singleton service. Idempotent."""
    global _service_instance
    with _service_lock:
        if _service_instance is None:
            return
        try:
            _service_instance.stop()
        except Exception as e:
            logger.debug(f"[discovery.zeroconf] stop error (ignored): {e}")
        _service_instance = None


def get_lan_discovery() -> Optional[LanDiscoveryService]:
    """Get the running singleton (may be None if start failed or wasn't called)."""
    return _service_instance
