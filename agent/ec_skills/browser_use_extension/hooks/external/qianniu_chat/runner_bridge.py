"""The 千牛 bundle as the platform sees it (``live_chat_dispatch.runner_bridge()``).

Native-desktop site: it has no browser/CDP, no page WebSocket, no DOM driver,
so it deliberately exposes NONE of the browser capabilities (dom, ws_session,
tab_pool, resolve_tab_target_id, send_message_tool_name, ...). Every platform
call site treats a missing attribute as "this site has no such capability" and
falls back to generic behaviour.

What it does expose: the site name (so the registry can key it and
``ECAN_LIVE_CHAT_SITE`` / ``set_active_site`` resolve), a trace label, and the
desktop typing lock that serialises sends. Sending itself is done by the
``qianniu_send`` MCP tool from the skill graph, not by the platform's browser
direct-delivery fast path — which is why no send-tool name is advertised here.
"""
from __future__ import annotations

from .typing_lock import get_lock

SITE = "qianniu_chat"


class QianniuRunnerBridge:
    site_plugin_name = SITE
    trace_label_prefix = "qianniu"

    @property
    def typing_lock(self):
        return get_lock()

    @property
    def node_tunable_number_fields(self):
        return []

    @property
    def node_tunable_bool_fields(self):
        return []


_BRIDGE = QianniuRunnerBridge()


def get_bridge() -> QianniuRunnerBridge:
    return _BRIDGE


def register() -> None:
    from agent.ec_skills import live_chat_dispatch
    live_chat_dispatch.register_runner_bridge(_BRIDGE, SITE)
