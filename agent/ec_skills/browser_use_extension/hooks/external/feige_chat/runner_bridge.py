"""Feige implementation of the runner's live-chat bridge (2026-08-01).

``ec_tasks/runner.py`` used to lazy-import a couple dozen Feige modules
directly (trace ledger, delivery durability, tab pool, typing lock,
DOM helpers, tunables, ...), which spread business-specific imports all
over platform code.  The runner now resolves every site capability
through ONE bridge object registered with
``agent.ec_skills.live_chat_dispatch.register_runner_bridge`` — this
module is the Feige bridge.

Design rules:

* Every attribute the runner touches must resolve lazily (property /
  method doing a local import) so importing this module stays cheap and
  cycle-free — several Feige modules import runner themselves.
* Attribute names are platform-neutral (``dispatch_state``,
  ``trace_ledger``, ``resolve_tab_target_id`` ...); anything
  Feige-branded (function names, env-var spellings, defaults) stays on
  this side of the boundary.
* A capability that raises must behave, from the runner's guarded call
  sites, exactly like the old failed lazy import: the runner wraps each
  use in try/except and falls back to its site-agnostic default.
"""
from __future__ import annotations

from typing import Any


class FeigeRunnerBridge:
    """Lazy facade over the feige_chat modules the runner needs."""

    # ------------------------------------------------------------------
    # Module namespaces (generic names → Feige modules).  Exposed as
    # properties so each import happens on first use, preserving the
    # exact laziness of the runner's old inline imports.
    # ------------------------------------------------------------------
    @property
    def dispatch_state(self):
        from . import dispatch_state
        return dispatch_state

    @property
    def hot_path(self):
        from . import hot_path
        return hot_path

    @property
    def hot_path_v2(self):
        from . import hot_path_v2
        return hot_path_v2

    @property
    def human_intervention(self):
        from . import human_intervention
        return human_intervention

    @property
    def relevance_judge(self):
        from . import human_relevance_judge
        return human_relevance_judge

    @property
    def placeholder_timer(self):
        from . import placeholder_timer
        return placeholder_timer

    @property
    def tab_pool(self):
        from . import tab_pool
        return tab_pool

    @property
    def typing_lock(self):
        from . import typing_lock
        return typing_lock

    @property
    def ws_session(self):
        from . import ws_session
        return ws_session

    @property
    def actionable_items(self):
        from . import actionable_items
        return actionable_items

    @property
    def delivery_durability(self):
        from . import delivery_durability
        return delivery_durability

    @property
    def trace_ledger(self):
        from . import trace_ledger
        return trace_ledger

    @property
    def drift_recovery(self):
        from . import drift_recovery_signal
        return drift_recovery_signal

    @property
    def undeliverable(self):
        from . import undeliverable
        return undeliverable

    # ------------------------------------------------------------------
    # Round-2 module accessors (2026-08-01): the remaining platform
    # files (event_monitor, frontdesk_dispatch, chat_tools, build_node,
    # extension_tools_service, ...) resolve these the same way the
    # runner does.  Feige-branded module names map to generic names on
    # this side of the boundary.
    # ------------------------------------------------------------------
    @property
    def system_message_filter(self):
        from . import system_message_filter
        return system_message_filter

    @property
    def pre_dispatch_enrich(self):
        from . import pre_dispatch_enrich
        return pre_dispatch_enrich

    @property
    def pre_dispatch_v2(self):
        from . import pre_dispatch_v2
        return pre_dispatch_v2

    @property
    def pre_dispatch_scrape_v2(self):
        from . import pre_dispatch_scrape_v2
        return pre_dispatch_scrape_v2

    @property
    def actionable_items_v2(self):
        from . import actionable_items_v2
        return actionable_items_v2

    @property
    def image_store(self):
        from . import image_store
        return image_store

    @property
    def image_fetch(self):
        from . import image_fetch
        return image_fetch

    @property
    def product_detail_store(self):
        from . import product_detail_store
        return product_detail_store

    @property
    def ws_observer(self):
        from . import ws_observer
        return ws_observer

    @property
    def ws_inbound_watchdog(self):
        from . import ws_inbound_watchdog
        return ws_inbound_watchdog

    @property
    def ws_reader(self):
        from . import ws_reader
        return ws_reader

    @property
    def ws_sender(self):
        from . import ws_sender
        return ws_sender

    @property
    def ws_raw_sender(self):
        from . import ws_raw_sender
        return ws_raw_sender

    @property
    def ws_coverage(self):
        from . import ws_coverage
        return ws_coverage

    @property
    def front_desk(self):
        from . import front_desk
        return front_desk

    @property
    def front_desk_hot_path_v2(self):
        from . import front_desk_hot_path_v2
        return front_desk_hot_path_v2

    @property
    def bot_control(self):
        from . import feige_bot_control
        return feige_bot_control

    @property
    def page_refresh(self):
        from . import feige_page_refresh
        return feige_page_refresh

    @property
    def cdp_lane(self):
        from . import feige_cdp_lane
        return feige_cdp_lane

    @property
    def quick_reply(self):
        from . import quick_reply_v2
        return quick_reply_v2

    @property
    def crosstalk_guard(self):
        from . import crosstalk_guard_v2
        return crosstalk_guard_v2

    @property
    def dormant_probe(self):
        from . import dormant_probe
        return dormant_probe

    @property
    def human_mode(self):
        from . import human_mode
        return human_mode

    @property
    def tab_lifecycle(self):
        from . import tab_lifecycle
        return tab_lifecycle

    @property
    def url_detector(self):
        from . import url_detector
        return url_detector

    @property
    def direct_delivery(self):
        from . import direct_delivery
        return direct_delivery

    @property
    def dom(self):
        # dom_assets exposes generic aliases for its site-branded
        # function names; platform code must use the generic aliases.
        from . import dom_assets
        return dom_assets

    @property
    def tunables(self):
        # Platform callers may use resolve_int/float/bool ONLY with
        # platform-neutral knob names; site-branded knobs get a typed
        # wrapper method on this bridge instead.
        from . import tunables
        return tunables

    @property
    def site_adapter_preset(self) -> dict:
        # Default per-site SiteAdapter config (selectors + verify policy)
        # consumed by hooks/builtin/site_adapter.normalize_site_adapter
        # when the caller supplies no adapter config (2026-08-01).
        from .site_adapter_preset import DEFAULT_SITE_ADAPTER
        return DEFAULT_SITE_ADAPTER

    @property
    def tool_name_glob(self) -> str:
        # Glob covering this bundle's registered browser-use tool family;
        # used by hooks/builtin/bypass_actions as the permitted-tools
        # fallback when rules don't name any tool (2026-08-01).
        return "feige_*"

    # ------------------------------------------------------------------
    # DOM helpers — wrapped because the Feige function names are
    # site-branded and dom_assets is too big to expose wholesale.
    # ------------------------------------------------------------------
    async def resolve_tab_target_id(self, session: Any, **kwargs: Any):
        from .dom_assets import resolve_feige_tab_target_id
        return await resolve_feige_tab_target_id(session, **kwargs)

    async def scrape_latest_customer_bubble(self, *args: Any, **kwargs: Any):
        from .dom_assets import scrape_latest_customer_bubble
        return await scrape_latest_customer_bubble(*args, **kwargs)

    # ------------------------------------------------------------------
    # Tunables — env-var spellings and defaults live in Feige's
    # tunables.py; the runner only asks for the resolved value.
    # ------------------------------------------------------------------
    def bypass_on_backpressure(self) -> bool:
        from .tunables import resolve_bool, DEFAULT_DIRECT_LIVE_CHAT_BYPASS_ON_BACKPRESSURE
        return resolve_bool(
            "DIRECT_FEIGE_BYPASS_ON_BACKPRESSURE",
            DEFAULT_DIRECT_LIVE_CHAT_BYPASS_ON_BACKPRESSURE,
            None,
        )

    def typing_concurrency(self) -> int:
        from .tunables import resolve_int, DEFAULT_FEIGE_TYPING_CONCURRENCY
        return resolve_int("FEIGE_TYPING_CONCURRENCY", DEFAULT_FEIGE_TYPING_CONCURRENCY, None)

    def tab_resolve_timeout_s(self) -> float:
        from .tunables import resolve_float, DEFAULT_FEIGE_TAB_RESOLVE_TIMEOUT_S
        return resolve_float(
            "FEIGE_TAB_RESOLVE_TIMEOUT_S", DEFAULT_FEIGE_TAB_RESOLVE_TIMEOUT_S, None
        )

    def hot_path_drift_retry_max(self) -> int:
        from .tunables import resolve_int, DEFAULT_HOT_PATH_DRIFT_RETRY_MAX
        return resolve_int("HOT_PATH_DRIFT_RETRY_MAX", DEFAULT_HOT_PATH_DRIFT_RETRY_MAX, None)

    def placeholder_timeout_s(self) -> float:
        """Per-turn placeholder-timer deadline in seconds (0 = disabled).
        Site-branded knob name + default stay on this side of the
        boundary (frontdesk_dispatch round 2, 2026-08-01)."""
        from .tunables import resolve_float, DEFAULT_FEIGE_PLACEHOLDER_TIMEOUT_S
        return resolve_float(
            "FEIGE_PLACEHOLDER_TIMEOUT_S", DEFAULT_FEIGE_PLACEHOLDER_TIMEOUT_S, None
        )

    # ------------------------------------------------------------------
    # Direct-delivery tool names (registered on the browser-use
    # controller).  The runner looks these up generically.
    # ------------------------------------------------------------------
    @property
    def open_session_tool_name(self) -> str:
        return "feige_open_session"

    @property
    def send_message_tool_name(self) -> str:
        return "feige_send_message"

    @property
    def list_sessions_tool_name(self) -> str:
        return "feige_list_sessions"

    # ------------------------------------------------------------------
    # Trace-label family prefix — extension_tools_service classifies CDP
    # evaluate trace labels as "live-chat site" work via this prefix
    # (timeout family, health cooldown, slow-eval tracker, trace ledger
    # routing) without spelling the site name (round 2, 2026-08-01).
    # ------------------------------------------------------------------
    @property
    def trace_label_prefix(self) -> str:
        return "feige_"

    # ------------------------------------------------------------------
    # PreDispatch site-plugin identity — frontdesk_dispatch matches the
    # node config's ``preDispatch.site_plugin`` value against this name
    # and loads ``pre_dispatch_enrich.enrich_item`` through the bridge
    # (frontdesk_dispatch round 2, 2026-08-01).
    # ------------------------------------------------------------------
    @property
    def site_plugin_name(self) -> str:
        return "feige_chat"

    # ------------------------------------------------------------------
    # Site-specific delivery-failure reason codes the runner should
    # treat as retryable (unioned with its generic set at check time).
    # ------------------------------------------------------------------
    @property
    def retryable_send_reasons(self) -> frozenset[str]:
        return frozenset({"tool_failed:feige_send_message"})

    # ------------------------------------------------------------------
    # Site-specific per-node tunable fields (skill-editor UI field name
    # -> runtime override key).  build_node merges these into its
    # generic table so the branded names stay bundle-side while
    # existing skill JSONs keep working unchanged.
    # ------------------------------------------------------------------
    @property
    def node_tunable_number_fields(self) -> "list[tuple[str, str]]":
        return [("feigeSendCdpEvaluateTimeoutS", "FEIGE_SEND_CDP_EVALUATE_TIMEOUT_S")]

    @property
    def node_tunable_bool_fields(self) -> "list[tuple[str, str]]":
        return [("directFeigeBypassOnBackpressure", "DIRECT_FEIGE_BYPASS_ON_BACKPRESSURE")]

    def classify_send_error(self, err: str) -> "str | None":
        """Map the send tool's site-specific error markers to the
        runner's generic outcome reason codes."""
        text = str(err or "")
        if "feige_send_unverified:mis_delivered_to_wrong_chat" in text:
            return "send_unverified_mis_delivered"
        if "feige_send_unverified:input_cleared_no_bubble" in text:
            return "send_unverified_no_bubble"
        return None

    # ------------------------------------------------------------------
    # CDP health cooldown — implementation currently lives in
    # extension_tools_service under a Feige-branded name; keep that
    # knowledge on this side of the boundary.
    # ------------------------------------------------------------------
    def cdp_health_cooldown_remaining(self) -> float:
        import sys
        _ets = sys.modules.get(
            "agent.ec_skills.browser_use_extension.extension_tools_service"
        )
        if _ets is None:
            from agent.ec_skills.browser_use_extension import extension_tools_service as _ets
        remaining_fn = getattr(_ets, "live_chat_cdp_health_cooldown_remaining", None)
        if callable(remaining_fn):
            return max(0.0, float(remaining_fn()))
        return 0.0

    def mark_cdp_unhealthy(self, reason: str = "", **kwargs: Any) -> float:
        """Open the site-send CDP health cooldown (used by e.g. the
        memory monitor's high-RSS protection)."""
        import sys
        _ets = sys.modules.get(
            "agent.ec_skills.browser_use_extension.extension_tools_service"
        )
        if _ets is None:
            from agent.ec_skills.browser_use_extension import extension_tools_service as _ets
        fn = getattr(_ets, "mark_live_chat_cdp_unhealthy", None)
        if callable(fn):
            return float(fn(reason, **kwargs) or 0.0)
        return 0.0

    def mark_cdp_healthy(self) -> None:
        import sys
        _ets = sys.modules.get(
            "agent.ec_skills.browser_use_extension.extension_tools_service"
        )
        if _ets is None:
            from agent.ec_skills.browser_use_extension import extension_tools_service as _ets
        fn = getattr(_ets, "mark_live_chat_cdp_healthy", None)
        if callable(fn):
            fn()


def register() -> None:
    """Register the Feige runner bridge (called from package __init__)."""
    from agent.ec_skills import live_chat_dispatch
    live_chat_dispatch.register_runner_bridge(FeigeRunnerBridge())
