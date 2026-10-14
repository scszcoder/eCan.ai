"""The 千牛 bundle as the platform sees it (``live_chat_dispatch.runner_bridge()``).

Native-desktop site: it has no browser/CDP, no page WebSocket, no DOM driver,
so it deliberately exposes NONE of the browser capabilities (dom, ws_session,
tab_pool, resolve_tab_target_id, send_message_tool_name, ...). Every platform
call site treats a missing attribute as "this site has no such capability" and
falls back to generic behaviour.

What it does expose: the site name (so the registry can key it and
``ECAN_LIVE_CHAT_SITE`` / ``set_active_site`` resolve), a trace label, the
desktop typing lock that serialises sends, and ``deliver_reply``: the runner's
reply direct-delivery path hands a Q&A agent's reply here and it is sent with
``qianniu_tools.send_reply`` (the ``qianniu_send`` checks, no browser, no
front-desk LLM turn). The skill graph's ``qianniu_send`` stays the fallback.
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

    def deliver_reply(self, payload: dict) -> bool:
        """Send a Q&A agent's reply ({customer_id, customer_name, response_text,
        source_latest_message}) straight to the buyer -- the runner's reply
        direct-delivery path, instead of a front-desk LLM turn that only turns
        the reply into this same qianniu_send. False = not sent; the front desk
        then takes the reply as before."""
        from agent.mcp.server.qianniu.qianniu_tools import send_reply
        from . import name_map
        uid = str(payload.get("customer_id") or payload.get("customer_name") or "").strip()
        given = str(payload.get("customer_name") or "").strip()
        name = name_map.name_for(uid) or (given if given and given != uid else "")
        expect = str(payload.get("source_latest_message") or "").strip()
        res = send_reply(name, str(payload.get("response_text") or ""), expect)
        return bool(res.get("chat_sent"))

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
