"""The Pinduoduo bundle as the platform sees it (``live_chat_dispatch.runner_bridge()``).

Only what detection and reply delivery need. Everything else the platform
may ask a bridge for is absent on purpose: every call site treats a missing
attribute as "this site has no such capability" and falls back to generic
behaviour (see the contract notes in README.md).
"""
from __future__ import annotations

import types

from . import dom, hot_path_v2, system_message_filter, ws_observer, ws_session
from .site_adapter_preset import DEFAULT_SITE_ADAPTER
from .typing_lock import get_lock

SITE = "pdd_chat"

# Failures that happen BEFORE anything was typed -- safe to try again. An
# unverified send (clicked, bubble not seen) is never retried: it may have landed.
_RETRYABLE_MARKERS = ("pdd_send_not_typed", "typing_lock_busy", "did not open")


def _is_retryable_send_error(err: str) -> bool:
    text = str(err or "")
    if "pdd_send_unverified" in text:
        return False
    return any(m in text for m in _RETRYABLE_MARKERS)


class PddRunnerBridge:
    site_plugin_name = SITE
    trace_label_prefix = "pdd"
    tool_name_glob = "pdd_*"
    list_sessions_tool_name = "pdd_list_sessions"
    open_session_tool_name = "pdd_open_session"
    send_message_tool_name = "pdd_send_message"
    get_thread_tool_name = "pdd_get_chat_thread"

    site_adapter_preset = DEFAULT_SITE_ADAPTER
    ws_observer = ws_observer
    ws_session = ws_session
    system_message_filter = system_message_filter
    hot_path_v2 = hot_path_v2
    hot_path = types.SimpleNamespace(_is_retryable_send_error=_is_retryable_send_error,
                                     HOT_PATH_DRIFT_RETRY_BACKOFF_S=0.6)
    dom = dom

    @property
    def typing_lock(self):
        return get_lock()

    async def resolve_tab_target_id(self, browser_session, customer_key: str = "", **kw):
        return await dom.resolve_tab_target_id(browser_session, customer_key=customer_key)

    def tab_resolve_timeout_s(self) -> float:
        return 8.0

    def typing_concurrency(self) -> int:
        return 1                        # one reply box per page

    def hot_path_drift_retry_max(self) -> int:
        return 2

    @property
    def retryable_send_reasons(self) -> frozenset:
        return frozenset({"tool_failed:pdd_send_message"})

    def classify_send_error(self, err: str):
        text = str(err or "")
        if "pdd_send_unverified" in text:
            return "send_unverified_no_bubble"
        return None

    @property
    def node_tunable_number_fields(self):
        return []

    @property
    def node_tunable_bool_fields(self):
        return []


_BRIDGE = PddRunnerBridge()


def get_bridge() -> PddRunnerBridge:
    return _BRIDGE


def register() -> None:
    from agent.ec_skills import live_chat_dispatch
    live_chat_dispatch.register_runner_bridge(_BRIDGE, SITE)
