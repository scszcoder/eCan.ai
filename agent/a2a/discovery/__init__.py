"""
eCan A2A Discovery — Phase 1 (LAN, additive).

Provides zeroconf / DNS-SD based discovery for eCan nodes and agents on the
local network, running alongside the legacy Commander/Platoon protocol in
``agent/network/network.py`` without changing its behavior.

Public entry points:
    - get_machine_id(user_data_home)  → stable per-install UUID
    - compute_auth_fp(org, target_id) → 8-char service-tag fingerprint
    - get_directory()                 → AgentDirectory singleton
    - start_lan_discovery(...)        → starts the zeroconf advertiser+listener
    - stop_lan_discovery()            → unregisters services and stops browsers

Phase 2 (AppSync directory + WAN relay) will extend ``AgentDirectory`` with
``update_wan_endpoint`` and ``a2a_send`` will route through it. Phase 1 is
read-only as far as A2A is concerned — existing callers are not affected.
"""

from agent.a2a.discovery.machine_id import get_machine_id
from agent.a2a.discovery.auth import compute_auth_fp, verify_auth_fp
from agent.a2a.discovery.directory import (
    AgentEndpoint,
    AgentDirectory,
    get_directory,
)
from agent.a2a.discovery.zeroconf_service import (
    start_lan_discovery,
    stop_lan_discovery,
    LanDiscoveryService,
)
from agent.a2a.discovery.cloud_directory import (
    AgentRegistration as CloudAgentRegistration,
    CloudDirectoryClient,
    start_cloud_directory,
    stop_cloud_directory,
    get_cloud_directory,
)
from agent.a2a.discovery.wan_relay import (
    publish_a2a_message,
    subscribe_a2a_inbox,
    send_via_wan,
)
from agent.a2a.discovery.router import (
    configure_router,
    send_to_agent,
    SendOutcome,
    SendResult,
    list_known_agents,
    transport_for,
)
from agent.a2a.discovery.query import (
    find_agents,
    find_one_agent,
    list_skills,
)
from agent.a2a.discovery.group import (
    GroupSendReport,
    send_to_group,
    send_to_skill,
    broadcast_to_role,
)

__all__ = [
    # machine identity
    "get_machine_id",
    # auth
    "compute_auth_fp",
    "verify_auth_fp",
    # directory
    "AgentEndpoint",
    "AgentDirectory",
    "get_directory",
    # LAN (Phase 1)
    "start_lan_discovery",
    "stop_lan_discovery",
    "LanDiscoveryService",
    # WAN (Phase 2)
    "CloudAgentRegistration",
    "CloudDirectoryClient",
    "start_cloud_directory",
    "stop_cloud_directory",
    "get_cloud_directory",
    "publish_a2a_message",
    "subscribe_a2a_inbox",
    "send_via_wan",
    # router
    "configure_router",
    "send_to_agent",
    "SendOutcome",
    "SendResult",
    "list_known_agents",
    "transport_for",
    # query (Phase 3)
    "find_agents",
    "find_one_agent",
    "list_skills",
    # group (Phase 3)
    "GroupSendReport",
    "send_to_group",
    "send_to_skill",
    "broadcast_to_role",
]
